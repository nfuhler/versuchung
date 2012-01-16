#!/usr/bin/python

from subprocess import *
from versuchung.files import CSV_File
import logging
import os
import resource
import thread
import time


def shell(command, *args):
    """
    executes 'command' in a shell

    returns a tuple with
        1. the command's standard output as list of lines
        2. the exitcode
    """
    os.environ["LC_ALL"] = "C"

    args = ["'%s'"%x.replace("'", "\'") for x in args]
    command = command % tuple(args)

    logging.debug("executing: " + command)
    p = Popen(command, stdout=PIPE, stderr=STDOUT, shell=True)
    (stdout, _)  = p.communicate() # ignore stderr
    p.wait()
    if len(stdout) > 0 and stdout[-1] == '\n':
        stdout = stdout[:-1]
    return (stdout.__str__().rsplit('\n'), p.returncode)


class PsMonitor(CSV_File):
    """Can be used as: **input parameter** and **output parameter**

    With this parameter the systems status during the experiment can
    be monitored. The tick interval can specified on creation and also
    what values should be captured.

    This parameter creates two :class:`~versuchung.files.CSV_File`
    one with the given name, and one with the suffix ".events". When
    the experiment starts the monitor fires up a thread which will
    every ``tick_interval`` milliseconds capture the status of the
    system and store the information as a row in the normal csv.

    If :meth:`~.shell` is used instead of
    :func:`~versuchung.execute.shell` the started shell processes are
    logged to the ``".events"``-file.

    A short example::

        class SimpleExperiment(Experiment):
            outputs = {"ps": PsMonitor("ps_monitor", tick_interval=100)}

            def run(self):
                shell = self.o.ps.shell
                shell("sleep 1")
                shell("seq 1 100000 | while read a; do echo > /dev/null; done")
                shell("sleep 1")

        experiment = SimpleExperiment()
        experiment(sys.argv)

    >>> experiment.o.ps.extract(["time", "net_send"])
    [[1326548338.701827, 0],
     [1326548338.810422, 3],
     [1326548338.913667, 0],
     [1326548339.016836, 0],
     [1326548339.119982, 2],
     ....

    """
    def __init__(self, default_filename = "", tick_interval=100, capture = ["cpu", "mem", "net", "disk"]):
        CSV_File.__init__(self, default_filename)
        self.tick_interval = tick_interval
        self.__running = True
        self.capture = capture

    def __get_cpu(self):
        return [self.psutil.cpu_percent()]

    def __get_memory(self):
        phymem = self.psutil.phymem_usage()
        virtmem = self.psutil.virtmem_usage()
        cached = self.psutil.cached_phymem()
        buffers = self.psutil.phymem_buffers()

        return [phymem.total, phymem.used, phymem.free,
                virtmem.total, virtmem.used, virtmem.free,
                cached, buffers]

    def __get_net(self):
        if not hasattr(self, "old_network_stat"):
            self.old_network_stat = self.psutil.network_io_counters()
        stat = self.psutil.network_io_counters()
        ret = [stat.bytes_sent - self.old_network_stat.bytes_sent,
               stat.bytes_recv - self.old_network_stat.bytes_recv]
        self.old_network_stat = stat
        return ret

    def __get_disk(self):
        if not hasattr(self, "old_disk_stat"):
            self.old_disk_stat = self.psutil.disk_io_counters()
        stat = self.psutil.disk_io_counters()
        ret = [stat.read_bytes  - self.old_disk_stat.read_bytes,
               stat.write_bytes - self.old_disk_stat.write_bytes]
        self.old_disk_stat = stat
        return ret


    def monitor_thread(self):
        try:
            import psutil
            self.psutil = psutil
        except ImportError:
            raise RuntimeError("Please install psutil to use PsMonitor")

        while self.__running:
            row = [time.time()]
            if "cpu" in self.capture:
                row += self.__get_cpu()
            else:
                row += [-1]

            if "mem" in self.capture:
                row += self.__get_memory()
            else:
                row += [-1,-1,-1,-1,-1,-1,-1,-1]

            if "net" in self.capture:
                row += self.__get_net()
            else:
                row += [-1,-1]

            if "disk" in self.capture:
                row += self.__get_disk()
            else:
                row += [-1,-1]

            assert len(row) == len(self.sample_keys)
            self.append(row)


            time.sleep(self.tick_interval/1000.0)

    def inp_extract_cmdline_parser(self, opts, args):
        CSV_File.inp_parser_extract(self, opts, None)
        self.event_file = CSV_File(self.path + ".events")

    def outp_setup_output(self):
        CSV_File.outp_setup_output(self)
        self.event_file = CSV_File(self.path + ".events")
        self.event_file.outp_setup_output()
        self.thread = thread.start_new_thread(self.monitor_thread, tuple())

    def outp_tear_down_output(self):
        self.__running = False
        time.sleep(self.tick_interval/1000.0)
        CSV_File.outp_tear_down_output(self)
        self.event_file.outp_tear_down_output()



    sample_keys = ["time", "cpu_percentage",
                   "phymem_total", "phymem_used", "phymem_free",
                   "virtmem_total", "virtmem_used", "virtmem_free",
                   "cached", "buffers", "net_send", "net_recv",
                   "disk_read", "disk_write"]

    """The various fields in the csv file are organized like the
    strings in this list. E.g. The unix time is the first field of the
    csv file."""

    def shell(self, command, *args):
        """Like :func:`~versuchung.execute.shell`, but logs the start
        and stop of the process in the ``".events"``-file."""

        _args = ["'%s'"%x.replace("'", "\'") for x in args]
        _command = command % tuple(_args)

        self.event_file.append([time.time(), "started", _command])
        shell(command, *args)
        self.event_file.append([time.time(), "stopped", _command])

    def extract(self, keys = ["time", "cpu_percentage"]):
        """Extract single columns from the captured
        information. Useful keys are defined in
        :attr:`~.sample_keys`"""
        indices = [self.sample_keys.index(x) for x in keys]
        ret = []
        for row in self.value:
            r = []
            for index in indices:
                r.append(row[index])
            ret.append(r)
        return ret

    def events(self):
        """Get the list of events. The format is ``[unix_time,
        event_name, event_description]``"""
        return self.event_file.value
