import os
import logging
import multiprocessing
import tornado.gen
import tornado.queues
import tornado.concurrent
import tornado.ioloop

import virtool.gen
import virtool.utils
import virtool.database

from virtool.hosts import AddHost
from virtool.samples import ImportReads
from virtool.indexes import RebuildIndex
from virtool.analysis import PathoscopeBowtie, PathoscopeSNAP, NuVs

logger = logging.getLogger(__name__)

#: A dict containing :class:`~.job.Job` subclasses keyed by their task names.
TASK_CLASSES = {
    "rebuild_index": RebuildIndex,
    "pathoscope_bowtie": PathoscopeBowtie,
    "pathoscope_snap": PathoscopeSNAP,
    "nuvs": NuVs,
    "add_host": AddHost,
    "import_reads": ImportReads
}


class Collection(virtool.database.Collection):
    """
    Provides functionality for managing active jobs and manipulating and reading the job documents in the MongoDB
    collection. This object is referred to as the **job manager** in this documentation.

    The job manager controls which jobs are running based on the job resource settings. Jobs that are running or are
    waiting for resources to become available are represented by instances of the :class:`~.job.Job` subclasses
    described in :data:`.TASK_CLASSES`. The job manager can create new active jobs and cancel existing active jobs. It

    Exposed methods allow clients to cancel and remove jobs. Internal methods also are provided for starting
    new jobs and interacting with separate job processes.

    """
    def __init__(self, dispatcher):
        super(Collection, self).__init__("jobs", dispatcher)

        # Database-specific attributes
        self.sync_projector.update({key: True for key in [
            "task",
            "status",
            "proc",
            "mem",
            "username",
            "args"
        ]})

        db_sync = virtool.utils.get_db_client(self.settings, True)

        db_sync.jobs.update({}, {
            "$unset": {
                "archived": ""
            }
        })

        #: A :class:`dict` containing dicts describing each running or waiting job.
        self.jobs_dict = {}

        #: A :class:`dict` used for keeping track of used system resources.
        self.used = {
            "proc": 0,
            "mem": 0
        }

        #: A :class:`dict` for keeping track of the number or running jobs for each task type.
        self.task_counts = {key: 0 for key in TASK_CLASSES}

        #: A :class:`multiprocessing.Queue` object used to communicate with job processes.
        self.message_queue = multiprocessing.Queue()

        #: A :class:`tornado.queues.Queue` object that accepts dicts describing updates to the jobs collection. Updates
        #: are performed in the order they are added to the queue, ensuring that status updates are added to job
        #: documents in the correct order. This is important as job updates can be generated in quick succession.
        self._action_queue = tornado.queues.Queue()

        # Calls the _perform_update method which runs endlessly. Waits for updates for the jobs collection to appear in
        # the update queue.
        tornado.ioloop.IOLoop.current().spawn_callback(self._perform_action)

        # Iterate through the jobs dict every 300 ms.
        self.dispatcher.server.add_periodic_callback(self.iterate, 300)

    @virtool.gen.coroutine
    def sync_processor(self, documents):
        """
        Overrides :meth:`.database.Collection.sync_processor`.

        Removes the ``status`` and ``args`` fields from the job document.

        Adds a ``username`` field, an ``added`` date taken from the first status entry in the job document, and
        ``state`` and ``progress`` fields taken from the most recent status entry in the job document.

        :param documents: a list of documents to process.
        :type documents: list

        :return: a list of processed documents.
        :rtype: list

        """
        documents = virtool.database.coerce_list(documents)

        for document in documents:
            status = document.pop("status")
            args = document.pop("args")

            last_update = status[-1]

            document.update({
                "state": last_update["state"],
                "stage": last_update["stage"],
                "added": str(status[0]["date"]),
                "progress": status[-1]["progress"],
                "username": args["username"]
            })

        return documents

    @virtool.gen.coroutine
    def new(self, task, task_args, proc, mem, username, job_id=None):
        """
        Start a new job. Inserts a new job document into the database, instantiates a new :class:`.Job` object, and
        creates a new job dict in :attr:`.jobs_dict`. New jobs are in the waiting state.

        :param task: the name of the task to spawn.
        :type task: str

        :param task_args: arguments to be passed to the new :class:`~.job.Job` object.
        :type task_args: dict

        :param proc: the number of processor cores to reserve for the job.
        :type proc: int

        :param mem: the number of GBs of memory to reserve for the job.
        :type mem: int

        :param username: the name of the user that started the job.
        :type username: str

        :param job_id: optionally provide a job id--one will be automatically generated otherwise.
        :type job_id: str or None

        :return: the response from the Mongo insert operation.
        :rtype: dict

        """
        # Generate a new random job id.
        if job_id is None:
            job_id = yield self.get_new_id()

        # Insert a document in the database describing the new job.
        response = yield self.insert({
            "_id": job_id,
            "task": task,
            "args": task_args,
            "proc": proc,
            "mem": mem,
            "username": username,
            "status": [{
                "state": "waiting",
                "stage": None,
                "error": None,
                "progress": 0,
                "date": virtool.utils.timestamp()
            }]
        })

        # Instantiate a new job object.
        job = TASK_CLASSES[task](
            job_id,
            self.settings.as_dict(),
            self.message_queue,
            task,
            task_args,
            proc,
            mem
        )

        # Add a dict describing the new job to jobs_dict.
        self.jobs_dict[job_id] = {
            "obj": job,
            "task": task,
            "started": False,
            "proc": proc,
            "mem": mem
        }

        return response

    @virtool.gen.exposed_method([])
    def detail(self, transaction):
        """
        Return detail for the passed job id to the requesting client.

        :param transaction: the transaction generated by the request.
        :type transaction: :class:`~.dispatcher.Transaction`

        :return: a boolean indicating success of the request and a dict containing the job detail.
        :rtype: tuple

        """
        detail = yield self.find_one({"_id": transaction.data["_id"]})

        detail["log"] = yield self.read_log(detail["_id"])

        return True, detail

    @virtool.gen.exposed_method(["cancel_job"])
    def cancel(self, transaction):
        """
        Cancel the job(s) or jobs identified by the job id(s) in ``transaction`` by calling :meth:`._cancel`.

        :param transaction: the transaction generated by the request.
        :type transaction: :class:`~.dispatcher.Transaction`

        :return: ``True`` and ``None``
        :rtype: tuple

        """
        # Make sure the id(s) are in a list.
        id_list = virtool.database.coerce_list(transaction.data["_id"])

        # Cancel the job(s) identified in id_list.
        yield self._cancel(id_list)

        return True, None

    @virtool.gen.coroutine
    def _cancel(self, id_list):
        """
        Cancel the jobs with the ids in ``id_list``.

        If a job is waiting to run, it is removed from the :attr:`.jobs_dict` and the job object's
        :meth:`~.Job.cleanup` method is called. A *cancelled* status entry is added to the job document by calling
        :meth:`.update_status`.

        If the job is running, the job object's :meth:`~.Job.terminate` method is called. The job object handles the
        SIGTERM and takes care of calling :meth:`~.Job.cleanup` and :meth:`.update_status`.

        :param id_list: the ids of the jobs that should be cancelled.
        :type id_list: list

        """
        for job_id in id_list:
            job_dict = self.jobs_dict[job_id]

            if job_dict["started"]:
                job_dict["obj"].terminate()

            # Just delete the job if it still waiting to be started
            else:
                yield self.update_status(job_id, 0, "cancelled", None)

                job_dict["obj"].cleanup()

                # self._to_remove.append(_id)
                self.jobs_dict.pop(job_id)

    @virtool.gen.exposed_method(["remove_job"])
    def remove_job(self, transaction):
        """
        Remove the job or jobs identified by the passed job id(s).

        :param transaction: the transaction generated by the request.
        :type transaction: :class:`~.dispatcher.Transaction`

        :return: ``True`` and the response from the Mongo remove operation.
        :rtype: tuple

        """
        data = transaction.data

        # Removed the documents associated with the job ids from the database.
        response = yield super(Collection, self).remove(data["_id"])

        # Remove the logs associated with the jobs that were removed.
        for job_id in virtool.database.coerce_list(data["_id"]):
            yield self.remove_log(job_id)

        return True, response

    @virtool.gen.coroutine
    def update(self, query, update, increment_version=True, upsert=False, connections=None):
        """
        Redefinition of :meth:`.database.Collection.update`. Instead of directly making an update to the database
        collection using Motor, the update is packaged as a tuple and pushed into :attr:`._update_queue`. The updates
        are pulled out of the queue by :meth:`._perform_update` and performed in the order. This prevents misordering
        of the *status* field in job documents.

        :param query:
        :type query: dict or str

        :param update:
        :type update: dict

        :param increment_version:
        :type increment_version: bool

        :param upsert:
        :type upsert: bool

        :param connections:
        :type connections: list

        :return: True
        :rtype: bool

        """
        data =  {
            "query": query,
            "update": update,
            "increment_version": increment_version,
            "upsert": upsert,
            "connections": connections
        }

        payload = (
            "update",
            data
        )

        self._action_queue.put(payload)

    @virtool.gen.coroutine
    def update_status(self, job_id, progress, state, stage, error=None):
        """
        Update the *status* field for the document identified by the passed ``job_id``.

        If only the progress field has changed, a new status item will not be added to the *status* field. Instead the
        last status item will be updated with the new progress value.

        If any other item fields have changed, a new status item will be pushed to the *status* field.

        :param job_id: the id of the job to update the status for.
        :type job_id: str

        :param progress: the progress of the job (0 - 1).
        :type progress: float

        :param state: the state of the job.
        :type state: str

        :param stage: the stage the job has reached.
        :type stage: str or None

        :param error: an error dict if an error has occurred.
        :type error: dict or None

        """
        data = {
            "job_id": job_id,
            "progress": progress,
            "state": state,
            "stage": stage,
            "error": error
        }

        payload = (
            "update_status",
            data
        )

        self._action_queue.put(payload)

    @virtool.gen.coroutine
    def _perform_action(self):
        """
        Endlessly looping method that takes update tuples from :attr:`._update_queue` and calls
        :meth:`.database.Collection.update` with the data from the update tuple.

        """
        while True:
            # Will yield the update tuple when data is pushed into the update queue.
            action, data = yield self._action_queue.get()

            # Perform the update using the parent class' update method.
            if action == "update":
                yield super(Collection, self).update(
                    data["query"],
                    data["update"],
                    increment_version=data["increment_version"]
                )

            if action == "update_status":
                job_id = data["job_id"]
                progress = data["progress"]
                state = data["state"]
                stage = data["stage"]
                error = data["error"]

                status = yield self.get_field(data["job_id"], "status")

                last_status = status[-1]

                if last_status["state"] == state and last_status["stage"] == stage and last_status["error"] == error:
                    status[-1]["progress"] = progress

                    yield super(Collection, self).update(job_id, {
                        "$set": {
                            "status": status
                        }
                    })

                else:
                    yield super(Collection, self).update(job_id, {
                        "$push": {
                            "status": {
                                "state": state,
                                "stage": stage,
                                "progress": progress,
                                "date": virtool.utils.timestamp(),
                                "error": error
                            }
                        }
                    })

            # Tells the queue to move onto the next item.
            self._action_queue.task_done()



    @tornado.gen.coroutine
    def iterate(self):
        """
        The central runtime method for the collection. When called, it:

        1. Checks for database operations sent from :class:`~.job.Job` objects via :attr:`queue` and performs
           them.

        2. Iterates through all jobs in :attr:`.jobs_dict` and starts waiting jobs for which resources are available and
           removes jobs that have been terminated.

        """
        while not self.message_queue.empty():
            message = self.message_queue.get()
            data = message["data"]

            if message["operation"] == "update_status":
                if data["error"]:
                    self.jobs_dict[data["_id"]]["obj"].terminate()

                self.update_status(
                    data["_id"],
                    data["progress"],
                    data["state"],
                    data["stage"],
                    data["error"]
                )

            else:
                method = getattr(self.dispatcher.collections[message["collection_name"]], message["operation"])

                try:
                    yield method(message["data"])
                except TypeError:
                    yield method()

        for job_id in list(self.jobs_dict.keys()):
            # Get job data.
            job_dict = self.jobs_dict[job_id]
            task = job_dict["task"]

            # Get the number of running jobs with the same task.
            task_count = self.task_counts[task]

            # Check if resources are available to run a waiting job
            if not job_dict["started"]:
                task_limit = self.settings.get(task + "_inst")

                if self.resources_available(job_dict["proc"], job_dict["mem"]) and task_count < task_limit:
                    # Reserve resources and task slots
                    for key in self.used:
                        self.used[key] += job_dict[key]

                    self.task_counts[task] += 1

                    # Start job
                    job_dict["started"] = True
                    job_dict["obj"].start()

            if job_dict["started"] and not job_dict["obj"].is_alive():
                # Join the job process.
                job_dict["obj"].join()

                # Release the resources reserved for the job.
                self.release_resources(job_id)

                # Add the job to a list of job_ids that should be removed
                del self.jobs_dict[job_id]

    def release_resources(self, job_id):
        """
        Releases resources consumed by the job identified by the passed ``job_id``.

        :param job_id: the id of the job to release resources for.
        :type job_id: str

        """
        # Get the dict for the job.
        job = self.jobs_dict[job_id]

        # Reduce the used resource counts by the amounts reserved for the job.
        for key in ["proc", "mem"]:
            self.used[key] -= job[key]

        # Decrement the global task count for the job task by one.
        self.task_counts[job["task"]] -= 1

    def resources_available(self, proc=0, mem=0):
        """
        Check if the given number proc and amount of memory are available.

        :param proc: the number of processor cores.
        :type proc: int

        :param mem: the number of GBs of memory.
        :type mem: int

        :return: boolean indicating whether the resources are available or not.
        :rtype: bool

        """
        return proc <= self.resources["available"]["proc"] and mem <= self.resources["available"]["mem"]

    @property
    def resources(self):
        """
        A method decorated by :class:`property` and exposed as an instance attribute that returns a dictionary of
        available and used resources as well as the global limits.

        """
        return {
            "used": dict(self.used.items()),
            "available": {key: self.settings.get(key) - self.used[key] for key in self.used},
            "limit": {key: self.settings.get(key) for key in self.used}
        }

    @virtool.gen.synchronous
    def read_log(self, job_id):
        """
        Return the log text for the given ``job_id``.

        :param job_id: the id of the job to return a log for.
        :type job_id: str

        :return: a list of line strings from the log file.
        :rtype: list

        """
        path = os.path.join(self.settings.get("data_path"), "logs/jobs", job_id + ".log")

        try:
            # Return a list of lines from the log file if it exists.
            with open(path, "r") as log_file:
                return [line.rstrip() for line in log_file]

        except OSError:
            # Return an empty list if the log file doesn't exist.
            return list()

    @virtool.gen.synchronous
    def remove_log(self, job_id):
        """
        Remove the log file for a given ``job_id``.

        :param job_id: the id of the job to remove the log file for.
        :type job_id: str

        :return: boolean indicating whether a log file was removed or not.
        :rtype: bool

        """
        try:
            # Calculate the log path and remove the log file. If it exists, return True.
            path = os.path.join(self.settings.get("data_path"), "logs/jobs", job_id + ".log")
            yield virtool.utils.rm(path)
            return True
        except OSError:
            # Return False if the log file does not exist.
            return False
