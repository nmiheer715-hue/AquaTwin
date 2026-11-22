"""Runs one app job in its own process (so parallel simulations work on
Windows). Reads <jobdir>/job.json, writes log.txt and status.json there.

    python -m aquatwin.worker <jobdir>
"""
import json
import os
import sys
import traceback


def main(jobdir):
    spec = json.load(open(os.path.join(jobdir, "job.json")))
    logf = open(os.path.join(jobdir, "log.txt"), "a", encoding="utf-8", buffering=1)

    def status(s, result=None):
        json.dump(dict(status=s, result=result), open(os.path.join(jobdir, "status.json"), "w"))

    def log(msg):
        logf.write(str(msg) + "\n")

    status("running")
    try:
        if spec["kind"] == "plan":
            from . import plan
            log(f"Planning sensors for {spec['name']}")
            p = plan.make_plan(spec["inp"], spec["name"], spec.get("loggers", 0), spec.get("existing", []),
                               jobdir, progress=log, max_zone_junctions=spec.get("max_zone_junctions", 300))
            status("done", dict(page="plan.html", summary=p["final"], existing=p["existing_coverage"]))
        else:
            from . import run
            r = run.run_job(os.path.join(jobdir, "config.json"), spec.get("truth"), progress=log)
            status("done", dict(page="dashboard.html", alarms=r["alarms"], evaluation=r["evaluation"]))
    except SystemExit as e:
        log(f"Stopped: {e}")
        status("failed")
    except Exception as e:
        log("Error: " + "".join(traceback.format_exception_only(type(e), e)).strip())
        log(traceback.format_exc(limit=4))
        status("failed")


if __name__ == "__main__":
    main(sys.argv[1])
