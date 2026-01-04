import threading
import time
import queue
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import partial
from itertools import count


class AsyncExecutor:
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.task_queue = queue.PriorityQueue()
        self.shutdown_event = threading.Event()
        self._counter = count()

        self.dispatcher_thread = threading.Thread(
            target=self._dispatcher,
            daemon=True
        )
        self.dispatcher_thread.start()

    # -----------------------------------------------------
    # Public API
    # -----------------------------------------------------

    def submit(
        self,
        func,
        *args,
        callback=None,
        retries=0,
        retry_delay=0.5,
        timeout=None,
        priority=10,
        context=None,
        **kwargs
    ):
        """
        Submit a task for async execution.

        callback: callable(result, error, context)
        retries: number of retry attempts
        retry_delay: delay between retries (seconds)
        timeout: per-attempt timeout
        priority: lower number = higher priority
        context: arbitrary object passed to callback
        """

        task_id = next(self._counter)

        self.task_queue.put((
            priority,
            task_id,
            func,
            args,
            kwargs,
            callback,
            retries,
            retry_delay,
            timeout,
            context
        ))

    def shutdown(self, wait=True):
        self.shutdown_event.set()
        self.dispatcher_thread.join()
        self.executor.shutdown(wait=wait)

    # -----------------------------------------------------
    # Internal Dispatcher
    # -----------------------------------------------------

    def _dispatcher(self):
        while not self.shutdown_event.is_set():
            try:
                task = self.task_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            (
                priority,
                task_id,
                func,
                args,
                kwargs,
                callback,
                retries,
                retry_delay,
                timeout,
                context
            ) = task

            future = self.executor.submit(
                self._execute_with_retries,
                func,
                args,
                kwargs,
                retries,
                retry_delay,
                timeout
            )

            if callback:
                future.add_done_callback(
                    partial(self._handle_callback, callback, context)
                )

    # -----------------------------------------------------
    # Execution Logic
    # -----------------------------------------------------

    def _execute_with_retries(
        self,
        func,
        args,
        kwargs,
        retries,
        retry_delay,
        timeout
    ):
        last_exception = None

        for attempt in range(retries + 1):
            try:
                future = self.executor.submit(func, *args, **kwargs)
                return future.result(timeout=timeout)

            except TimeoutError as e:
                last_exception = TimeoutError(
                    f"Timeout after {timeout}s"
                )

            except Exception as e:
                last_exception = e

            if attempt < retries:
                time.sleep(retry_delay)

        raise last_exception

    # -----------------------------------------------------
    # Callback Handling
    # -----------------------------------------------------

    def _handle_callback(self, callback, context, future):
        try:
            result = future.result()
            callback(result, None, context)

        except Exception as e:
            callback(None, e, context)
