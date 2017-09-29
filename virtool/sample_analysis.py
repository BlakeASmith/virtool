"""
Functions and job classes for sample analysis.

"""
import os
import shutil
import aiofiles
from Bio import SeqIO

import virtool.app_settings
import virtool.blast
import virtool.job
import virtool.pathoscope
import virtool.sample
import virtool.utils
import virtool.virus
import virtool.virus_history
import virtool.virus_hmm
import virtool.virus_index


LIST_PROJECTION = [
    "_id",
    "algorithm",
    "created_at",
    "ready",
    "job",
    "index",
    "user",
    "sample"
]


async def new(db, settings, manager, sample_id, user_id, algorithm):
    """
    Creates a new analysis. Ensures that a valid subtraction host was the submitted. Configures read and write
    permissions on the sample document and assigns it a creator username based on the requesting connection.

    """
    # Get the current id and version of the virus index currently being used for analysis.
    index_id, index_version = await virtool.virus_index.get_current_index(db)

    sample = await db.samples.find_one(sample_id, ["name"])

    analysis_id = await virtool.utils.get_new_id(db.analyses)

    job_id = await virtool.utils.get_new_id(db.jobs)

    document = {
        "_id": analysis_id,
        "ready": False,
        "created_at": virtool.utils.timestamp(),
        "job": {
            "id": job_id
        },
        "algorithm": algorithm,
        "sample": {
            "id": sample_id
        },
        "index": {
            "id": index_id,
            "version": index_version
        },
        "user": {
            "id": user_id,
        }
    }

    sequence_virus_map = dict()
    virus_dict = dict()

    async for sequence_document in db.sequences.find({}, ["virus_id", "isolate_id"]):
        virus_id = sequence_document["virus_id"]

        virus = virus_dict.get(virus_id, None)

        if virus is None:
            virus = await db.viruses.find_one(virus_id, ["last_indexed_version"])

            try:
                last_index_version = virus["last_indexed_version"]

                virus_dict[virus["_id"]] = {
                    "id": virus["_id"],
                    "version": last_index_version
                }

                sequence_virus_map[sequence_document["_id"]] = virus_id
            except KeyError:
                virus_dict[virus["id"]] = False

        sequence_virus_map[sequence_document["_id"]] = virus_id

    sequence_virus_map = [item for item in sequence_virus_map.items()]

    await db.analyses.insert_one(document)

    task_args = dict(
        analysis_id=analysis_id,
        sample_id=sample_id,
        sample_name=sample["name"],
        index_id=index_id,
        virus_dict=virus_dict,
        sequence_virus_map=sequence_virus_map
    )

    # Clone the arguments passed from the client and amend the resulting dictionary with the analysis entry
    # _id. This dictionary will be passed the the new analysis job.
    await manager.new(
        document["algorithm"],
        task_args,
        user_id,
        job_id=job_id
    )

    await virtool.sample.recalculate_algorithm_tags(db, sample_id)

    return document


async def format_analysis(db, analysis):
    if "pathoscope" in analysis["algorithm"]:
        formatted = dict()

        for hit in analysis["diagnosis"]:

            virus_id = hit["virus"]["id"]
            version = hit["virus"]["version"]

            virus = formatted.get(virus_id, None)

            if virus is None:
                # Get the virus entry (patched to correct version).
                _, virus_document, _ = await virtool.virus_history.patch_virus_to_version(
                    db,
                    virus_id,
                    version
                )

                max_ref_length = 0

                for isolate in virus_document["isolates"]:
                    max_ref_length = max(max_ref_length, max([len(s["sequence"]) for s in isolate["sequences"]]))

                virus = {
                    "id": virus_id,
                    "name": virus_document["name"],
                    "version": virus_document["version"],
                    "abbreviation": virus_document["abbreviation"],
                    "isolates": virus_document["isolates"],
                    "length": max_ref_length
                }

                formatted[virus_id] = virus

            for isolate in virus["isolates"]:
                for sequence in isolate["sequences"]:
                    if sequence["_id"] == hit["id"]:
                        sequence.update(hit)
                        sequence["length"] = len(sequence["sequence"])

                        del sequence["virus"]
                        del sequence["virus_id"]
                        del sequence["isolate_id"]

        analysis["diagnosis"] = [formatted[virus_id] for virus_id in formatted]

        for virus in analysis["diagnosis"]:
            for isolate in list(virus["isolates"]):
                if not any("pi" in sequence for sequence in isolate["sequences"]):
                    virus["isolates"].remove(isolate)
                    continue

                for sequence in isolate["sequences"]:
                    if "pi" not in sequence:
                        sequence.update({
                            "pi": 0,
                            "reads": 0,
                            "coverage": 0,
                            "best": 0,
                            "length": len(sequence["sequence"])
                        })

                    sequence["id"] = sequence.pop("_id")

                    del sequence["sequence"]

        return analysis

    if analysis["algorithm"] == "nuvs":
        for hmm_result in analysis["hmm"]:
            hmm = await db.hmm.find_one({"_id": hmm_result["hit"]}, [
                "cluster",
                "families",
                "definition",
                "label"
            ])

            hmm_result.update(hmm)

    return analysis


class Base(virtool.job.Job):
    """
    A base class for all analysis job objects. Functions include:

    - establishing synchronous database connection
    - extracting task args to attributes
    - retrieving the sample and host documents
    - calculating the sample read count
    - constructing paths used by all subclasses

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        #: The document id for the sample being analyzed. and the analysis document the results will be committed to.
        self.sample_id = self.task_args["sample_id"]

        #: The document id for the analysis being run.
        self.analysis_id = self.task_args["analysis_id"]

        self.sequence_virus_map = {item[0]: item[1] for item in self.task_args["sequence_virus_map"]}

        self.virus_dict = self.task_args["virus_dict"]

        #: Stores data that is processed and stored in the analysis document.
        self.results = dict()

        #: Intermediate data dict.
        self.intermediate = dict()

        #: The document for the sample being analyzed. Assigned after database connection is made.
        self.sample = None

        #: The document for the host associated with the sample being analyzed. Assigned after database connection is
        # made.
        self.host = None

        #: The number of reads in the sample library. Assigned after database connection is made.
        self.read_count = None

        # The path to the general data directory
        self.data_path = self.settings.get("data_path")

        # The parent folder for all data associated with the sample
        self.sample_path = os.path.join(self.data_path, "samples", self.sample_id)

        # The path to the directory where all analysis result files will be written.
        self.analysis_path = os.path.join(self.sample_path, "analysis", self.analysis_id)

        self.index_path = os.path.join(
            self.data_path,
            "reference",
            "viruses",
            self.task_args["index_id"],
            "reference"
        )

        self.host_path = None

        self._stage_list = [
            self.check_db,
            self.mk_analysis_dir
        ]

        self.sample = None

        self.read_paths = None

        #: The document for the host associated with the sample being analyzed. Assigned after job start.
        self.host = None

        #: The number of reads in the sample library. Assigned after job start.
        self.read_count = None

    @virtool.job.stage_method
    async def check_db(self):
        """
        Get some initial information from the database that will be required during the course of the job.

        """
        # Get the complete sample document from the database.
        self.sample = await self.db.samples.find_one({"_id": self.sample_id})

        # Extract the sample read count from the sample document.
        self.read_count = int(self.sample["quality"]["count"])

        # Calculate the path(s) to the sample read file(s).
        self.read_paths = [os.path.join(self.sample_path, "reads_1.fastq")]

        if self.sample.get("paired", False):
            self.read_paths.append(os.path.join(self.sample_path, "reads_2.fastq"))

        # Get the complete host document from the database.
        self.host = await self.db.hosts.find_one({"_id": self.sample["subtraction"]["id"]})

        self.host_path = os.path.join(
            self.data_path,
            "reference",
            "hosts",
            self.sample["subtraction"]["id"].lower().replace(" ", "_"),
            "reference"
        )

    @virtool.job.stage_method
    async def mk_analysis_dir(self):
        """
        Make a directory for the analysis in the sample/analysis directory.

        """
        await self.run_in_executor(os.mkdir, self.analysis_path)

    async def cleanup(self):
        """
        Remove the analysis document and the analysis files. Dispatch the removal op.

        Recalculate the algorithm tags for the sample document and dispatch the new processed document.

        """
        await self.db.analyses.delete_one({"_id": self.analysis_id})

        await self.dispatch("analyses", "remove", [self.analysis_id])

        try:
            await self.loop.run_in_executor(None, shutil.rmtree, self.analysis_path)
        except FileNotFoundError:
            pass

        document = await virtool.sample.recalculate_algorithm_tags(self.db, self.sample_id)

        await self.dispatch("samples", "update", document)


class Pathoscope(Base):

    """
    A base class for all Pathoscope-based tasks. Subclass of :class:`.sample_analysis.Base`.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @virtool.job.stage_method
    async def generate_isolate_fasta(self):
        """
        Identifies virus hits from the initial default virus mapping.

        """
        fasta_path = os.path.join(self.analysis_path, "isolate_index.fa")

        sequence_ids = self.intermediate["to_host"]

        # Get the database documents for the sequences
        async with aiofiles.open(fasta_path, "w") as handle:
            # Iterate through each virus id referenced by the hit sequence ids.
            for virus_id in await self.db.sequences.distinct("virus_id", {"_id": {"$in": sequence_ids}}):
                # Write all of the sequences for each virus to a FASTA file.
                async for document in self.db.sequences.find({"virus_id": virus_id}, ["sequence"]):
                    await handle.write(">{}\n{}\n".format(document["_id"], document["sequence"]))

        del self.intermediate["to_host"]

    @virtool.job.stage_method
    async def subtract_mapping(self):
        """
        Subtracts virus and host alignments stored in :attr:`.intermediate` as :class:`virtool.pathoscope.sam.Lines`
        objects. Reads that have a higher alignment score to the host than to the virus reference are eliminated from
        the analysis.

        """
        subtracted_count = await self.run_in_executor(
            virtool.pathoscope.subtract,
            self.analysis_path,
            self.intermediate["to_host"]
        )
        
        del self.intermediate["to_host"]
        
        self.results["subtracted_count"] = subtracted_count

    @virtool.job.stage_method
    async def pathoscope(self):
        """
        Run the Pathoscope reassignment algorithm. Tab-separated output is written to ``pathoscope.tsv``. Results are
        also parsed and saved to :attr:`intermediate`.

        """
        vta_path = os.path.join(self.analysis_path, "to_isolates.vta")

        u, nu, refs, reads = await self.run_in_executor(virtool.pathoscope.build_matrix, vta_path)

        best_hit_initial_reads, best_hit_initial, level_1_initial, level_2_initial = await self.run_in_executor(
            virtool.pathoscope.compute_best_hit,
            u,
            nu,
            refs,
            reads
        )

        init_pi, pi, _, nu = await self.run_in_executor(virtool.pathoscope.em, u, nu, refs, 50, 1e-7, 0, 0)

        best_hit_final_reads, best_hit_final, level_1_final, level_2_final = await self.run_in_executor(
            virtool.pathoscope.compute_best_hit,
            u,
            nu,
            refs,
            reads
        )

        read_count = len(reads)

        report = await self.run_in_executor(
            virtool.pathoscope.write_report,
            os.path.join(self.analysis_path, "report.tsv"),
            pi,
            refs,
            read_count,
            init_pi,
            best_hit_initial,
            best_hit_initial_reads,
            best_hit_final,
            best_hit_final_reads,
            level_1_initial,
            level_2_initial,
            level_1_final,
            level_2_final
        )

        reassigned_path = os.path.join(self.analysis_path, "reassigned.vta")

        await self.run_in_executor(virtool.pathoscope.rewrite_align, u, nu, vta_path, 0.01, reassigned_path)

        self.intermediate["coverage"] = await self.run_in_executor(
            virtool.pathoscope.calculate_coverage,
            reassigned_path,
            self.intermediate["ref_lengths"]
        )

        self.results = {
            "ready": True,
            "read_count": read_count,
            "diagnosis": list()
        }

        for ref_id, hit in report.items():
            # Get the virus info for the sequence id.
            virus = self.virus_dict[self.sequence_virus_map[ref_id]]

            # Make sure it is not ``False`` (meaning the virus had not ``last_indexed_version`` field).
            assert virus

            hit["id"] = ref_id

            # Attach "virus" (id, version) to the hit.
            hit["virus"] = virus

            # Get the coverage for the sequence.
            hit_coverage = self.intermediate["coverage"][ref_id]

            # Attach coverage list to hit dict.
            hit["align"] = hit_coverage

            # Calculate coverage and attach to hit.
            hit["coverage"] = round(1 - hit_coverage.count(0) / len(hit_coverage), 3)

            # Calculate depth and attach to hit.
            hit["depth"] = round(sum(hit_coverage) / len(hit_coverage))

            self.results["diagnosis"].append(hit)

    @virtool.job.stage_method
    async def import_results(self):
        """
        Commits the results to the database. Data includes the output of Pathoscope, final mapped read count,
        and viral genome coverage maps.

        Once the import is complete, :meth:`cleanup_index_files` is called to remove
        any virus indexes that may become unused when this analysis completes.

        """
        await self.db.analyses.update_one({"_id": self.analysis_id}, {
            "$set": self.results
        })

        document = await virtool.sample.recalculate_algorithm_tags(self.db, self.sample_id)

        await self.dispatch("samples", "update", document)

    @virtool.job.stage_method
    async def cleanup_indexes(self):
        pass


class PathoscopeBowtie(Pathoscope):

    """
    A Pathoscope analysis job that uses Bowtie2 to map reads to viral and host references. The ad-hoc isolate index
    is built using ``bowtie2-build``.

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._stage_list = [
            self.check_db,
            self.mk_analysis_dir,
            self.map_viruses,
            self.generate_isolate_fasta,
            self.build_isolate_index,
            self.map_isolates,
            self.map_subtraction,
            self.subtract_mapping,
            self.pathoscope,
            self.import_results,
            self.cleanup_indexes
        ]

    @virtool.job.stage_method
    async def map_viruses(self):
        """
        Using ``bowtie2``, maps reads to the main virus reference. This mapping is used to identify candidate viruses.

        """
        command = [
            "bowtie2",
            "-p", str(self.proc),
            "--no-unal",
            "--local",
            "--score-min", "L,20,1.0",
            "-N", "0",
            "-L", "15",
            "-x", self.index_path,
            "-U", ",".join(self.read_paths)
        ]

        to_viruses = set()

        ref_lengths = dict()

        async def stdout_handler(line):
            line = line.decode()

            if line[0] == "#":
                return

            if line[0] == "@":
                if line[1:3] == "SQ":
                    for field in line.split("\t"):
                        split_field = field.split(":")

                        if split_field[0] == "SN":
                            ref_id = split_field[1]
                        if split_field[0] == "LN":
                            length = int(split_field[1])

                    ref_lengths[ref_id] = length

                return

            fields = line.split("\t")

            # Bitwise FLAG - 0x4: segment unmapped
            if int(fields[1]) & 0x4 == 4:
                return

            ref_id = fields[2]

            if ref_id == "*":
                return

            # Skip if the p_score does not meet the minimum cutoff.
            if virtool.pathoscope.find_sam_align_score(fields) < 0.01:
                return

            to_viruses.add(ref_id)

        await self.run_subprocess(command, stdout_handler=stdout_handler)

        self.intermediate["to_viruses"] = to_viruses

    @virtool.job.stage_method
    async def build_isolate_index(self):
        """
        Build an index with ``bowtie2-build`` from the FASTA file generated by
        :meth:`Pathoscope.generate_isolate_fasta`.

        """
        command = [
            "bowtie2-build",
            os.path.join(self.analysis_path, "isolate_index.fa"),
            os.path.join(self.analysis_path, "isolates")
        ]

        await self.run_subprocess(command)

    @virtool.job.stage_method
    async def map_isolates(self):
        """
        Using ``bowtie2``, map the sample reads to the index built using :meth:`.build_isolate_index`.

        """
        command = [
            "bowtie2",
            "-p", str(self.proc - 1),
            "--no-unal",
            "--local",
            "--score-min", "L,20,1.0",
            "-N", "0",
            "-L", "15",
            "-k", "100",
            "--al", os.path.join(self.analysis_path, "mapped.fastq"),
            "-x", os.path.join(self.analysis_path, "isolates"),
            "-U", ",".join(self.read_paths)
        ]

        out_handle = await aiofiles.open(os.path.join(self.analysis_path, "to_isolates.vta"), "w")

        async def stdout_handler(line, p_score_cutoff=0.01):
            line = line.decode()

            if line[0] == "@" or line == "#":
                return

            fields = line.split("\t")

            # Bitwise FLAG - 0x4 : segment unmapped
            if int(fields[1]) & 0x4 == 4:
                return

            ref_id = fields[2]

            if ref_id == "*":
                return

            p_score = virtool.pathoscope.find_sam_align_score(fields)

            # Skip if the p_score does not meet the minimum cutoff.
            if p_score < p_score_cutoff:
                return

            await out_handle.write(",".join([
                fields[0],  # read_id
                ref_id,
                fields[3],  # pos
                str(len(fields[9])),  # length
                str(p_score)
            ]) + "\n")

        await self.run_subprocess(command, stdout_handler=stdout_handler)

        await out_handle.close()

    @virtool.job.stage_method
    async def map_subtraction(self):
        """
        Using ``bowtie2``, map the reads that were successfully mapped in :meth:`.map_isolates` to the subtraction host
        for the sample.

        """
        command = [
            "bowtie2",
            "--local",
            "-N", "0",
            "-p", str(self.proc - 1),
            "-x", self.host_path,
            "-U", os.path.join(self.analysis_path, "mapped.fastq")
        ]

        to_host = dict()

        async def stdout_handler(line):
            line = line.decode()

            if line[0] == "@" or line == "#":
                return

            fields = line.split("\t")

            # Bitwise FLAG - 0x4 : segment unmapped
            if int(fields[1]) & 0x4 == 4:
                return

            # No ref_id assigned.
            if fields[2] == "*":
                return

            to_host[fields[0]] = virtool.pathoscope.find_sam_align_score(fields)

        await self.run_subprocess(command, stdout_handler=stdout_handler)

        self.intermediate["to_host"] = to_host


class NuVs(Base):

    """
    A job class for NuVs, a custom workflow used for identifying potential viral sequences from sample libraries. The
    workflow consists of the following steps:

    1. Eliminate known viral reads by mapping the sample reads to the Virtool virus reference using ``bowtie2`` saving
       unaligned reads.
    2. Eliminate known host reads by mapping the reads remaining from the previous stage to the sample's subtraction
       host using ``bowtie2`` and saving the unaligned reads.
    3. Generate an assembly from the remaining reads using SPAdes.
    4. Extract all significant open reading frames (ORF) from the assembled contigs.
    5. Using HMMER/vFAM, identify possible viral domains in the ORFs.

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._stage_list += [
            self.map_viruses,
            self.map_host,
            self.reunite_pairs,
            self.assemble,
            self.process_fasta,
            self.press_hmm,
            self.vfam,
            self.import_results
        ]

    @virtool.job.stage_method
    async def map_viruses(self):
        """
        Maps reads to the main virus reference using ``bowtie2``. Bowtie2 is set to use the search parameter
        ``--very-fast-local`` and retain unaligned reads to the FASTA file ``unmapped_viruses.fq``.

        """
        command = [
            "bowtie2",
            "-p", str(self.proc),
            "-k", str(1),
            "--very-fast-local",
            "-x", self.index_path,
            "--un", os.path.join(self.analysis_path, "/unmapped_viruses.fq"),
            "-U", ",".join(self.read_paths)
        ]

        await self.run_subprocess(command)

    @virtool.job.stage_method
    async def map_host(self):
        """
        Maps unaligned reads from :meth:`.map_viruses` to the sample's subtraction host using ``bowtie2``. Bowtie2 is
        set to use the search parameter ``--very-fast-local`` and retain unaligned reads to the FASTA file
        ``unmapped_host.fq``.

        """
        command = [
            "bowtie2",
            "--very-fast-local",
            "-k", str(1),
            "-p", str(self.proc),
            "-x", self.host_path,
            "--un", os.path.join(self.analysis_path, "unmapped_hosts.fq"),
            "-U", os.path.join(self.analysis_path, "unmapped_viruses.fq"),
        ]

        await self.run_subprocess(command)

    @virtool.job.stage_method
    async def reunite_pairs(self):
        if self.sample["paired"]:
            with open(os.path.join(self.analysis_path, "unmapped_hosts.fq"), "rU") as handle:
                unmapped_roots = {record.id.split(" ")[0] for record in SeqIO.parse(handle, "fastq")}

            with open(self.read_paths[0], "r") as handle:
                s_dict = {record.id.split(" ")[0]: record for record in SeqIO.parse(handle, "fastq")}

                with open(os.path.join(self.analysis_path, "unmapped_1.fq"), "w") as unmapped:
                    for root in unmapped_roots:
                        SeqIO.write(s_dict[root], unmapped, "fastq")

            with open(self.read_paths[1], "r") as handle:
                s_dict = {record.id.split(" ")[0]: record for record in SeqIO.parse(handle, "fastq")}

                with open(os.path.join(self.analysis_path, "unmapped_2.fq"), "w") as unmapped:
                    for root in unmapped_roots:
                        SeqIO.write(s_dict[root], unmapped, "fastq")

    @virtool.job.stage_method
    async def assemble(self):
        """
        Call ``spades.py`` to assemble contigs from ``unmapped_hosts.fq``. Passes ``21,33,55,75`` for the ``-k``
        argument.

        """
        command = [
            "spades.py",
            "-t", str(self.proc - 1),
            "-m", str(self.mem)
        ]

        if self.sample["paired"]:
            command += [
                "-1", os.path.join(self.analysis_path, "unmapped_1.fq"),
                "-2", os.path.join(self.analysis_path, "unmapped_2.fq"),
            ]
        else:
            command += [
                "-s", os.path.join(self.analysis_path, "unmapped_hosts.fq"),
            ]

        command += [
            "-o", os.path.join(self.analysis_path, "spades"),
            "-k", "21,33,55,75"
        ]

        await self.run_subprocess(command)

    @virtool.job.stage_method
    def process_fasta(self):
        """
        Finds ORFs in the contigs assembled by :meth:`.assemble`. Only ORFs that are 100+ amino acids long are recorded.
        Contigs with no acceptable ORFs are discarded.

        """
        # Contigs that contain at least one acceptable ORF.
        self.results["sequences"] = list()

        # Acceptable ORFs found in assembled contigs.
        self.results["orfs"] = list()

        # A numeric index to identify the assembled contig. Increments by one for each FASTA entry.
        index = 0

        spades_path = os.path.join(self.analysis_path, "spades")

        fasta_path = os.path.join(spades_path, "scaffolds.fasta")

        for record in SeqIO.parse(fasta_path, "fasta"):

            seq_len = len(record.seq)

            orf_count = 0

            # Only look for ORFs if the contig is at least 300 nucleotides long.
            if seq_len > 300:
                # Looks at both forward (+) and reverse (-) strands.
                for strand, nuc in [(+1, record.seq), (-1, record.seq.reverse_complement())]:
                    # Look in all three translation frames.
                    for frame in range(3):
                        trans = str(nuc[frame:].translate(1))
                        trans_len = len(trans)
                        aa_start = 0

                        # Extract ORFs.
                        while aa_start < trans_len:
                            aa_end = trans.find("*", aa_start)

                            if aa_end == -1:
                                aa_end = trans_len
                            if aa_end - aa_start >= 100:
                                if strand == 1:
                                    start = frame + aa_start * 3
                                    end = min(seq_len, frame + aa_end * 3 + 3)
                                else:
                                    start = seq_len - frame - aa_end * 3 - 3
                                    end = seq_len - frame - aa_start * 3

                                self.results["orfs"].append({
                                    "index": index,
                                    "orf_index": orf_count,
                                    "pro": str(trans[aa_start:aa_end]),
                                    "nuc": str(nuc[start:end]),
                                    "frame": frame,
                                    "strand": strand,
                                    "pos": (start, end)
                                })

                                orf_count += 1

                            aa_start = aa_end + 1

            # Save the contig sequence if it contains at least one acceptable ORF.
            if orf_count > 0:
                self.results["sequences"].append(str(record.seq))
                index += 1

        # Write the ORFs to a FASTA file so that they can be analyzed using HMMER and vFAM.
        with open(os.path.join(self.analysis_path, "candidates.fa"), "w") as candidates:
            for entry in self.results["orfs"]:
                candidates.write(">sequence_{}.{}\n{}\n".format(
                    str(entry["index"]),
                    str(entry["orf_index"]),
                    entry["pro"]
                ))

    @virtool.job.stage_method
    def press_hmm(self):

        shutil.copy(os.path.join(self.data_path, "hmm", "profiles.hmm"), self.analysis_path)

        hmm_path = os.path.join(self.analysis_path, "profiles.hmm")

        command = [
            "hmmpress",
            hmm_path
        ]

        self.run_subprocess(command)

        os.remove(hmm_path)

    @virtool.job.stage_method
    async def vfam(self):
        """
        Searches for viral motifs in ORF translations generated by :meth:`.process_fasta`. Calls ``hmmscan`` and
        searches against ``candidates.fa`` using the profile HMMs in ``data_path/hmm/vFam.hmm``.

        Saves two files:

        - ``hmm.tsv`` contains the raw output of `hmmer`
        - ``hits.tsv`` contains the `hmmer` results formatted and annotated with the annotations from the Virtool HMM
          database collection

        """
        self.results["hmm"] = list()

        # The path to output the hmmer results to.
        tsv_path = os.path.join(self.analysis_path, "hmm.tsv")

        command = [
            "hmmscan",
            "--tblout", tsv_path,
            "--noali",
            "--cpu", str(self.proc - 1),
            os.path.join(self.analysis_path, "profiles.hmm"),
            os.path.join(self.analysis_path, "candidates.fa")
        ]

        await self.run_subprocess(command)

        # The column titles for the ``hits.tsv`` output file.
        header = [
            "index",
            "orf_index",
            "hit",
            "full_e",
            "full_score",
            "full_bias",
            "best_e",
            "best_bias",
            "best_score"
        ]

        # The path to write ``hits.tsv`` to.
        hit_path = os.path.join(self.self.analysis_path, "hits.tsv")

        # Go through the raw HMMER results and annotate the HMM hits with data from the database.
        with open(tsv_path, "r") as hmm_file:
            with open(hit_path, "w") as hit_file:
                hit_file.write(",".join(header))

                for line in hmm_file:
                    if line.startswith("vFam"):
                        line = line.split()

                        cluster_id = int(line[0].split("_")[1])
                        annotation_id = self.db.hmm.find_one({"cluster": int(cluster_id)}, {"_id": True})["_id"]

                        compound_id = line[2].split("_")[1].split(".")

                        entry = {
                            "index": int(compound_id[0]),
                            "orf_index": int(compound_id[1]),
                            "hit": annotation_id,
                            "full_e": float(line[4]),
                            "full_score": float(line[5]),
                            "full_bias": float(line[6]),
                            "best_e": float(line[7]),
                            "best_bias": float(line[8]),
                            "best_score": float(line[9])
                        }

                        self.results["hmm"].append(entry)

                        joined = ",".join(["{}".format(entry[key]) for key in header])

                        hit_file.write(joined + "\n")

    @virtool.job.stage_method
    async def import_results(self):
        """
        Import into the analysis document in the database the following data:

        - the sequences with significant ORFs in them
        - all significant ORF sequences and metadata
        - the annotated HMMER results from ``hits.tsv``

        After the import is complete, :meth:`.indexes.Collection.cleanup_index_files` is called to remove any virus
        indexes that are no longer being used by an active analysis job.

        """
        referenced = [entry["index"] for entry in self.results["hmm"]]

        self.results["sequences"] = [
            {"sequence": seq, "index": i} for i, seq in enumerate(self.results["sequences"]) if i in referenced
        ]

        retained = [entry["index"] for entry in self.results["sequences"]]

        self.results["orfs"] = [orf for orf in self.results["orfs"] if orf["index"] in retained]

        self.call_static("set_analysis", self.sample_id, self.analysis_id, self.results)

        await virtool.virus_index.cleanup_index_files(manager.db, manager.settings)

    @staticmethod
    async def set_analysis(manager, sample_id, analysis_id, data):
        """
        Update the analysis document identified using ``data``, which contains the analysis id and the update. Sets the
        analysis' ``ready`` field to ``True``. Sets the parent sample's ``analyzed`` field to ``True`` and increments
        its version by one.

        """
        db = manager.db

        document = await db.analyses.find_one({"_id": analysis_id})
        document.update(dict(data, ready=True))

        await db.analyses.update_one({"_id": analysis_id}, {
            "$set": document
        })

        await db.samples.update_one({"_id": sample_id}, {
            "$set": {"nuvs": True}
        })