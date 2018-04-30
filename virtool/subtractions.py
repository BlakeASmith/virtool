import os
import logging

logger = logging.getLogger(__name__)


def calculate_fasta_gc(path):
    nucleotides = {
        "a": 0,
        "t": 0,
        "g": 0,
        "c": 0,
        "n": 0
    }

    count = 0

    # Go through the fasta file getting the nucleotide counts, lengths, and number of sequences
    with open(path, "r") as handle:
        for line in handle:
            if line[0] == ">":
                count += 1
                continue

            for i in ["a", "t", "g", "c", "n"]:
                # Find lowercase and uppercase nucleotide characters
                nucleotides[i] += line.lower().count(i)

    nucleotides_sum = sum(nucleotides.values())

    return {k: round(nucleotides[k] / nucleotides_sum, 3) for k in nucleotides}, count


def calculate_index_path(settings, subtraction_id):
    return os.path.join(
        settings.get("data_path"),
        "subtractions",
        subtraction_id.replace(" ", "_").lower()
    )
