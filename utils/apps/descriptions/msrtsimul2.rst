msrtsimul2 is an extended version of :ref:`msrtsimul`. It simulates real-time
data acquisition by injecting miniSEED data from a file into the seedlink buffer
via the mseedfifo plugin for seedlink. It can be used for simulating real-time
conditions in playbacks for whole-system demonstrations, user training, etc.

The data is played back as if they were recorded at current time. Therefore,
creation times and the actual data times including pick times, event times etc.
will be **obscured**. :ref:`Historic playbacks <sec-msrtsimul2-historic>` allow
keeping the actual data times.

In addition to all options of :ref:`msrtsimul`, msrtsimul2 adds:

* Compressed input (:file:`.gz`, :file:`.bz2`) decompressed transparently.
* :option:`--filter` to select specific streams by NSLC pattern.
* :option:`--sort` to sort unsorted input without a separate scmssort step.
* :option:`--inject-jump` to pre-fill the SeedLink buffer during the jump window.
* :option:`--start-time`, :option:`--end-time`, :option:`--duration` for precise time window selection.
* :option:`--loop` to repeat playback indefinitely.
* :option:`--fifo` to write to an arbitrary named pipe path.
* :option:`-q` / :option:`--quiet` to suppress the startup banner and summary.
* Proper :mod:`logging` module integration with :option:`-v` / :option:`-vv` levels.
* NTP-safe pacing using ``time.monotonic()`` to avoid bursts during long playbacks.
* End-of-run summary: elapsed time, records written/skipped, stream count.

.. hint::

   * Playbacks on production systems are normally not recommended.
   * For real-time playbacks, the data must be sorted by end time. This
     requirement may be violated. Use :ref:`scmssort` for sorting the data by
     (end) time, or use the :option:`--sort` flag.
   * Stop :ref:`slarchive` before running msrtsimul2 to avoid archiving data
     with wrong times.
   * Normally, :ref:`seedlink` assumes records of 512 bytes. msrtsimul2 warns
     when detecting records of other sizes.
   * Data in other record sizes can be repacked to 512 bytes with
     :program:`msrepack` from :cite:t:`libmseed-github`.
   * Use :option:`--unlimited` to accept records of any size when SeedLink is
     compiled to support them.


Non-default seedlink pipes
--------------------------

By default, msrtsimul2 writes the data into the mseedfifo pipe
*$SEISCOMP_ROOT/var/run/seedlink/mseedfifo*.

* :option:`--seedlink` replaces *seedlink* with another instance name, e.g.
  **seedlink-test**, writing to *$SEISCOMP_ROOT/var/run/seedlink-test/mseedfifo*.
* :option:`--fifo` writes directly to an arbitrary named pipe path.
* :option:`--stdout` writes to standard output for redirection.


.. _sec-msrtsimul2-historic:

Historic playbacks
------------------

Use :option:`-m` *historic* to preserve original record times, so that picks,
amplitudes and origins keep their original timestamps. The system clock is
untouched. GUI, processing modules and logging run with current system time.
This allows processing waveforms with the stream inventory valid at the time the
data were recorded, including streams closed at current time.

Make sure :ref:`scautopick` is started with :option:`--playback`. Example setup:

.. code-block:: sh

   seiscomp stop
   rm -rf $SEISCOMP_ROOT/var/lib/seedlink/buffer
   seiscomp start
   msrtsimul2 -m historic miniSEED-file


Compressed input files
----------------------

msrtsimul2 transparently decompresses :file:`.gz` and :file:`.bz2` files.
No extra flags are needed:

.. code-block:: sh

   msrtsimul2 event.mseed.gz
   msrtsimul2 event.mseed.bz2


Sorting unsorted input
----------------------

The input file must be sorted by end_time for correct real-time pacing.
Use :option:`--sort` to sort at startup when pre-sorting with :ref:`scmssort`
is not practical:

.. code-block:: sh

   msrtsimul2 --sort unsorted.mseed

.. note::

   :option:`--sort` reads the entire file into memory. For large files it is
   more efficient to pre-sort with :ref:`scmssort`:

   .. code-block:: sh

      scmssort -u -E 'unsorted.mseed' > sorted.mseed
      msrtsimul2 sorted.mseed


Stream filtering
----------------

The :option:`--filter` option accepts a *NET.STA.LOC.CHA* pattern with wildcards
``*`` and ``?`` and can be specified multiple times. Only matching streams are
injected:

.. code-block:: sh

   msrtsimul2 --filter 'AU.*.*.BHZ' --filter 'IU.CTAO.*.*' miniSEED-file


Time window selection
---------------------

* :option:`--start-time` — skip records before this UTC timestamp.
* :option:`--end-time` — stop when records reach this UTC timestamp.
* :option:`--duration` — limit to this many seconds; absolute with
  :option:`--start-time`, relative to first record otherwise.


Pre-filling the buffer with jumped data
----------------------------------------

Use :option:`--jump` together with :option:`--inject-jump` to push the
pre-event window into SeedLink at full speed before real-time playback begins.
This is required by modules such as :ref:`scautomt` that need a minimum of
continuous waveform data (e.g. 12 minutes) before the event origin time:

.. code-block:: sh

   msrtsimul2 --jump 12 --inject-jump miniSEED-file


Looping
-------

:option:`--loop` repeats playback from the beginning of the file after EOF.
Not available when reading from stdin.


seedlink setup
--------------

For supporting msrtsimul2 activate the :confval:`msrtsimul` parameter in the
seedlink module configuration (:file:`seedlink.cfg`), update the configuration
and restart seedlink before running msrtsimul2:

.. code-block:: sh

   seiscomp update-config seedlink
   seiscomp restart seedlink
   msrtsimul2 ...


Examples
--------

1. Playback miniSEED waveforms in real time with verbose output:

   .. code-block:: sh

      msrtsimul2 -v miniSEED-file

#. Playback in historic mode:

   .. code-block:: sh

      msrtsimul2 -v -m historic miniSEED-file

#. Feed data into a specific seedlink instance, e.g. *seedlink-test*:

   .. code-block:: sh

      msrtsimul2 --seedlink seedlink-test miniSEED-file

#. Inject only broadband vertical channels from the AU network:

   .. code-block:: sh

      msrtsimul2 --filter 'AU.*.*.BHZ' miniSEED-file

#. Inject a 10-minute window starting at a specific time:

   .. code-block:: sh

      msrtsimul2 --start-time 2023-06-01T04:30:00 --duration 600 miniSEED-file

#. Inject 12 minutes of pre-event data at full speed, then continue in real time:

   .. code-block:: sh

      msrtsimul2 --jump 12 --inject-jump miniSEED-file

#. Play a compressed file at double speed, quiet mode (for scripted use):

   .. code-block:: sh

      msrtsimul2 -q -s 2 event.mseed.gz

#. Loop a short event file continuously for demonstration purposes:

   .. code-block:: sh

      msrtsimul2 --loop miniSEED-file
