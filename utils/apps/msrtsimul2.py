#!/usr/bin/env seiscomp-python

from __future__ import absolute_import, division, print_function

import bz2
import calendar
import datetime
import fnmatch
import gzip
import logging
import math
import os
import stat
import sys
import time
from argparse import ArgumentParser

from seiscomp import mseedlite as mseed


logger = logging.getLogger("msrtsimul2")


# ------------------------------------------------------------------------------
def open_input(path):
    """Open a MiniSEED file for reading, transparently decompressing gz/bz2."""
    if path.endswith(".gz"):
        return gzip.open(path, "rb")
    if path.endswith(".bz2"):
        return bz2.open(path, "rb")
    return open(path, "rb")


# ------------------------------------------------------------------------------
def read_mseed_with_delays(delaydict, reciterable):
    """
    Create an iterator which takes into account configurable realistic delays.

    A delaydict has the following data structure:
    keys: XX.ABC (XX: network code, ABC: station code). The key "default" is
    a special value for the default delay.
    values: Delay to be introduced in seconds
    """
    import heapq  # pylint: disable=C0415

    heap = []
    min_delay = 0
    default_delay = 0
    if "default" in delaydict:
        default_delay = delaydict["default"]
    for rec in reciterable:
        rec_time = calendar.timegm(rec.end_time.timetuple())
        stationname = f"{rec.net}.{rec.sta}"
        if stationname in delaydict:
            delay_time = rec_time + delaydict[stationname]
        else:
            delay_time = rec_time + default_delay
        heapq.heappush(heap, (delay_time, rec))
        toprectime = heap[0][0]
        if toprectime - min_delay < rec_time:
            topelement = heapq.heappop(heap)
            yield topelement
    while heap:
        topelement = heapq.heappop(heap)
        yield topelement


# ------------------------------------------------------------------------------
def rt_simul(f, speed=1.0, jump=0.0, inject_jump=False, sort=False, delaydict=None):
    """
    Iterator to simulate "real-time" MSeed input

    Records are read in pseudo-real-time relative to the time of the first
    record, resulting in data flowing at realistic speed.

    The data in the input file may be multiplexed, but *must* be sorted by
    time unless sort=True is given (e.g. pre-sorted using scmssort).

    When sort=True the entire file is read into memory and sorted by end_time
    before playback begins. This is a one-time startup cost proportional to
    file size.

    When inject_jump is True, records within the jump window are yielded at
    full speed (no pacing) instead of being discarded. This pre-fills the
    SeedLink buffer with historical data before the real-time portion starts,
    which is required by modules like scautomt that need a buffer of waveforms
    prior to the event origin time.

    Uses time.monotonic() for pacing so that NTP clock adjustments during
    long playbacks do not cause bursts or pauses.
    """
    # time.monotonic() is used for pacing: immune to NTP clock jumps.
    rtime = time.monotonic()
    etime = None
    skipping = True

    record_iterable = mseed.Input(f)
    if sort:
        logger.info("Sorting records by end_time (reads entire file into memory)")
        record_iterable = iter(sorted(record_iterable, key=lambda r: r.end_time))
    if delaydict:
        record_iterable = read_mseed_with_delays(delaydict, record_iterable)

    for rec in record_iterable:
        if delaydict:
            rec_time = rec[0]
            rec = rec[1]
        else:
            rec_time = calendar.timegm(rec.end_time.timetuple())
        if etime is None:
            etime = rec_time

        if skipping:
            if (rec_time - etime) / 60.0 < jump:
                if inject_jump:
                    yield rec  # inject at full speed to pre-fill buffer
                continue
            etime = rec_time
            skipping = False

        tmax = etime + speed * (time.monotonic() - rtime)
        ms = 1000000.0 * (rec.nsamp / rec.fsamp)
        last_sample_time = rec.begin_time + datetime.timedelta(microseconds=ms)
        last_sample_time = calendar.timegm(last_sample_time.timetuple())
        if last_sample_time > tmax:
            time.sleep((last_sample_time - tmax + 0.001) / speed)
        yield rec


# ------------------------------------------------------------------------------
def parse_args():
    parser = ArgumentParser(
        prog="msrtsimul2",
        description=(
            "MiniSEED real-time playback and simulation. Reads sorted (and possibly "
            "multiplexed) miniSEED files and writes individual records in pseudo-real-time. "
            "Useful for testing and simulating data acquisition. Output is "
            "$SEISCOMP_ROOT/var/run/seedlink/mseedfifo unless --seedlink, --fifo or -c is used."
        ),
    )

    parser.add_argument(
        "file",
        nargs="?",
        metavar="miniSEED-file",
        help=(
            "MiniSEED file to read. Omit or use '-' to read from stdin. "
            "Compressed files (.gz, .bz2) are decompressed transparently."
        ),
    )

    grp_v = parser.add_argument_group("Verbosity")
    grp_v.add_argument(
        "-v", "--verbose",
        action="count", default=0,
        help="Increase verbosity. -v prints each record; -vv enables debug output.",
    )
    grp_v.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress startup banner and end-of-run summary. Warnings and errors are still shown.",
    )

    grp_p = parser.add_argument_group("Playback")
    grp_p.add_argument(
        "-c", "--stdout",
        action="store_true",
        help="Write to standard output.",
    )
    grp_p.add_argument(
        "-d", "--delays",
        metavar="FILE",
        help="File with per-station delays (one 'NET.STA: seconds' entry per line).",
    )
    grp_p.add_argument(
        "--fifo",
        metavar="PATH",
        help="Write directly to this named pipe path (overrides --seedlink).",
    )
    grp_p.add_argument(
        "--filter",
        metavar="NET.STA.LOC.CHA",
        action="append", dest="filters",
        help=(
            "Only inject streams matching this pattern (wildcards * and ? accepted). "
            "May be specified multiple times, e.g. --filter AU.*.*.BHZ --filter IU.CTAO.*.*"
        ),
    )
    grp_p.add_argument(
        "-j", "--jump",
        type=float, default=0.0, metavar="MINUTES",
        help="Minutes to skip at the beginning (float).",
    )
    grp_p.add_argument(
        "--inject-jump",
        action="store_true",
        help=(
            "Inject jumped records at full speed instead of discarding them. "
            "Useful when downstream modules (e.g. scautomt) require a waveform buffer "
            "before the event: use --jump to set the pre-event window and --inject-jump "
            "to push those records into SeedLink at maximum speed before real-time playback begins."
        ),
    )
    grp_p.add_argument(
        "--loop",
        action="store_true",
        help="Repeat playback from the beginning when the file ends (not valid with stdin).",
    )
    grp_p.add_argument(
        "-m", "--mode",
        choices=["realtime", "historic"], default="realtime",
        help=(
            "Playback mode: 'realtime' (default, record times shifted to now) "
            "or 'historic' (record times preserved)."
        ),
    )
    grp_p.add_argument(
        "--seedlink",
        default="seedlink", metavar="NAME",
        help=(
            "SeedLink module name. Replaces 'seedlink' in the default mseedfifo path. "
            "Useful for seedlink aliases or non-standard instance names."
        ),
    )
    grp_p.add_argument(
        "-s", "--speed",
        type=float, default=1.0, metavar="FACTOR",
        help="Speed factor (float, default: 1.0).",
    )
    grp_p.add_argument(
        "--sort",
        action="store_true",
        help=(
            "Sort records by end_time before playback. "
            "Reads the entire file into memory at startup — use only when "
            "the input is not already time-ordered and running scmssort first "
            "is not practical. Not available when reading from stdin."
        ),
    )
    grp_p.add_argument(
        "--start-time",
        metavar="DATETIME",
        help=(
            "Only inject records at or after this UTC time "
            "(ISO 8601, e.g. 2023-01-01T12:00:00). "
            "For large skips prefer --jump which avoids pacing over skipped records."
        ),
    )
    grp_p.add_argument(
        "--end-time",
        metavar="DATETIME",
        help="Stop injecting records once they reach this UTC time (ISO 8601).",
    )
    grp_p.add_argument(
        "--duration",
        type=float, metavar="SECONDS",
        help=(
            "Maximum playback window in seconds. "
            "With --start-time sets an absolute end time; "
            "otherwise measured from the first injected record."
        ),
    )
    grp_p.add_argument(
        "--test",
        action="store_true",
        help="Test mode: read and process records but do not write output.",
    )
    grp_p.add_argument(
        "-u", "--unlimited",
        action="store_true",
        help=(
            "Allow miniSEED records of any size. "
            "By default only 512-byte records are passed; "
            "others can be repacked with msrepack from libmseed."
        ),
    )

    return parser.parse_args()


# ------------------------------------------------------------------------------
def setup_logging(verbosity):
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    if verbosity == 0:
        logger.setLevel(logging.WARNING)
    elif verbosity == 1:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)


# ------------------------------------------------------------------------------
def parse_datetime(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Cannot parse datetime '{s}'. Expected ISO 8601, e.g. 2023-01-01T12:00:00"
    )


# ------------------------------------------------------------------------------
def matches_filters(rec, filters):
    if not filters:
        return True
    nslc = f"{rec.net}.{rec.sta}.{rec.loc}.{rec.cha}"
    return any(fnmatch.fnmatch(nslc, pat) for pat in filters)


# ------------------------------------------------------------------------------
def open_output(args):
    if args.test:
        logger.info("Test mode: output suppressed")
        return open(os.devnull, "wb")

    if args.stdout:
        logger.info("Output: stdout")
        return sys.stdout.buffer

    if args.fifo:
        fifo_path = args.fifo
    else:
        try:
            sc_root = os.environ["SEISCOMP_ROOT"]
        except KeyError:
            print("SEISCOMP_ROOT environment variable is not set", file=sys.stderr)
            sys.exit(1)
        fifo_path = os.path.join(sc_root, "var", "run", args.seedlink, "mseedfifo")

    logger.info(f"Output: {fifo_path}")

    if not os.path.exists(fifo_path):
        print(
            f"ERROR: {fifo_path} does not exist.\n"
            "In order to push the records to SeedLink, it needs to run and "
            "must be configured for real-time playback.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not stat.S_ISFIFO(os.stat(fifo_path).st_mode):
        print(
            f"ERROR: {fifo_path} is not a named pipe.\n"
            "Check if SeedLink is running and configured for real-time playback.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return open(fifo_path, "wb")
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


# ------------------------------------------------------------------------------
def main():
    args = parse_args()
    setup_logging(args.verbose)

    # Resolve time bounds
    start_time = None
    end_time = None
    if args.start_time:
        try:
            start_time = parse_datetime(args.start_time)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    if args.end_time:
        try:
            end_time = parse_datetime(args.end_time)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    if args.duration is not None and start_time is not None:
        end_time = start_time + datetime.timedelta(seconds=args.duration)

    # Open input
    from_stdin = not args.file or args.file == "-"
    if from_stdin:
        logger.info("Input: stdin")
        ifile = sys.stdin.buffer
        if args.sort:
            print("WARNING: --sort ignored when reading from stdin", file=sys.stderr)
            args.sort = False
    else:
        logger.info(f"Input: {args.file}")
        try:
            ifile = open_input(args.file)
        except IOError as e:
            print(f"ERROR: could not open '{args.file}': {e}", file=sys.stderr)
            sys.exit(1)

    if args.loop and from_stdin:
        print("WARNING: --loop ignored when reading from stdin", file=sys.stderr)
        args.loop = False

    # Parse delay file
    delaydict = None
    if args.delays:
        delaydict = {}
        try:
            with open(args.delays, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    content = line.split(":")
                    if len(content) != 2:
                        raise ValueError(f"Cannot parse line: {line!r}")
                    delaydict[content[0].strip()] = float(content[1].strip())
        except Exception as e:
            print(f"ERROR reading delay file '{args.delays}': {e}", file=sys.stderr)
            sys.exit(1)

    out_channel = open_output(args)

    # Run statistics
    n_written = 0
    n_skipped_size = 0
    n_skipped_filter = 0
    streams_seen = set()
    t_start = time.time()
    loop_count = 0

    if not args.quiet:
        print(
            f"Starting msrtsimul2 at {datetime.datetime.now(datetime.UTC)}",
            file=sys.stderr,
        )

    try:
        while True:
            if loop_count > 0:
                ifile.seek(0)
                logger.info(f"Starting loop {loop_count + 1}")

            inp = rt_simul(
                ifile,
                speed=args.speed,
                jump=args.jump,
                inject_jump=args.inject_jump,
                sort=args.sort,
                delaydict=delaydict,
            )
            time_diff = None
            duration_anchor = None

            for rec in inp:
                nslc = f"{rec.net}.{rec.sta}.{rec.loc}.{rec.cha}"

                # Absolute start time filter
                if start_time is not None and rec.begin_time < start_time:
                    logger.debug(f"Pre-window skip: {nslc} {rec.begin_time}")
                    continue

                # Absolute end time (also covers start_time + duration)
                if end_time is not None and rec.begin_time >= end_time:
                    logger.debug(f"Post-window stop at {rec.begin_time}")
                    break

                # Relative duration from first injected record (no --start-time)
                if args.duration is not None and start_time is None:
                    if duration_anchor is None:
                        duration_anchor = rec.begin_time
                    elif (rec.begin_time - duration_anchor).total_seconds() >= args.duration:
                        break

                # Stream filter
                if not matches_filters(rec, args.filters):
                    n_skipped_filter += 1
                    logger.debug(f"Filtered: {nslc}")
                    continue

                # Record size check
                if not args.unlimited and rec.size != 512:
                    logger.warning(
                        f"Skipping {nslc} {rec.begin_time}: size {rec.size} != 512 bytes"
                    )
                    n_skipped_size += 1
                    continue

                # Normalize record type so SeedLink accepts the record
                if rec.rectype not in ("D", "R", "Q"):
                    rec.rectype = "D"

                # Compute realtime offset once from the first injected record
                if time_diff is None:
                    ms = 1000000.0 * (rec.nsamp / rec.fsamp)
                    time_diff = (
                        datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                        - rec.begin_time
                        - datetime.timedelta(microseconds=ms)
                    )

                if args.mode == "realtime":
                    rec.begin_time += time_diff

                streams_seen.add(nslc)

                if logger.isEnabledFor(logging.INFO):
                    tdiff_to_start = time.time() - t_start
                    tdiff_to_current = time.time() - calendar.timegm(
                        rec.begin_time.timetuple()
                    )
                    print(
                        f"{nslc:<17} {tdiff_to_start:7.2f}s {rec.begin_time} "
                        f"{tdiff_to_current:7.2f}s",
                        file=sys.stderr,
                    )

                if not args.test:
                    rec.write(out_channel, int(math.log2(rec.size)))
                    out_channel.flush()

                n_written += 1

            if not args.loop:
                break
            loop_count += 1

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1
    finally:
        if not from_stdin:
            ifile.close()
        if not args.stdout and not args.test:
            out_channel.close()

    if not args.quiet:
        elapsed = time.time() - t_start
        loop_info = f", {loop_count} extra loop(s)" if loop_count > 0 else ""
        print(
            f"msrtsimul2 finished: {elapsed:.1f}s elapsed | "
            f"{n_written} records written | "
            f"{n_skipped_size} skipped (size) | "
            f"{n_skipped_filter} skipped (filter) | "
            f"{len(streams_seen)} streams{loop_info}",
            file=sys.stderr,
        )

    return 0


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(main())
