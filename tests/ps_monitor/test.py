from versuchung.experiment import Experiment
from versuchung.execute import shell, PsMonitor

class SimpleExperiment(Experiment):
    outputs = {"ps": PsMonitor("ps_monitor", tick_interval=10)}

    def run(self):
        shell = self.o.ps.shell
        shell("sleep 0.5")
        shell("seq 1 100 | while read a; do echo > /dev/null; done")
        shell("sleep 0.5")

if __name__ == "__main__":
    import shutil, sys
    experiment = SimpleExperiment()
    dirname = experiment(sys.argv)

    if dirname:
        shutil.rmtree(dirname)
    print "success"
