msrtsimul simulates a real-time data acquisition by injecting miniSEED data from a
file into the seedlink buffer via the mseedfifo plugin for seedlink. It can be
used for simulating real-time conditions in playbacks for whole-system
demonstrations, user training, etc.

The data is played back as if they were recorded at current time. Therefore,
creation times and the actual data times including pick times, event times etc.
will be **obscured**. :ref:`Historic playbacks <sec-msrtsimul-historic>` allow
keeping the actual data times.

.. hint::

   * Playbacks on production systems are normally not recommended.
   * For real-time playbacks, the data must be sorted by end time. This
     requirement may be violated. Use :ref:`scmssort` for sorting the data by
     (end) time.
   * Stop :ref:`slarchive` before running msrtsimul for avoiding that data with
     wrong times are archived.
   * Normally, :ref:`seedlink` assumes that the data is provided in records of
     512 bytes. msrtsimul issues a warning when detecting a record of other size.
   * Data available in other record sizes can be repacked to 512 bytes by
     external software such as :program:`msrepack` available with
     :cite:t:`libmseed-github`.
   * Applications other than standard :ref:`seedlink` in |scname| or
     :ref:`seedlink` compiled specifically may accept other record sizes. For
     accepting these records use msrtsimul with :option:`--unlimited`.


Non-default seedlink pipes
--------------------------

By default, msrtsimul writes the data into the mseedfifo pipe
*$SEISCOMP_ROOT/var/run/seedlink/mseedfifo*.
If the data is to be written into the pipe of a :program:`seedlink` alias or
into any other pipe, the pipe name must be adjusted. Use the option

* :option:`--seedlink` to replace *seedlink* by another name, e.g. a seedlink instance
  created as an alias, **seedlink-test**. This would write into
  *$SEISCOMP_ROOT/var/run/seedlink-test/mseedfifo*.
* :option:`--fifo` to write directly to an arbitrary named pipe path, regardless
  of the standard directory structure.
* :option:`--stdout` to write to standard output and then redirect to any other location.


.. _sec-msrtsimul-historic:

Historic playbacks
------------------

You may use msrtsimul with the :option:`-m` *historic* option to maintain the
time of the records,
thus the times of picks, amplitudes, origins, etc. but not the creation times.
Applying :option:`-m` *historic* will feed the data into the seedlink buffer at the time
of the records. The time of the system is untouched. GUI, processing modules, logging,
etc. will run with current system time. The historic mode allows to process waveforms
with the stream inventory valid at the time when the data were recorded including
streams closed at current time.

.. warning::

   When repeating historic playbacks, the waveforms are fed multiple times to the
   seedlink buffer and the resulting picks are also repeated with the same pick
   times. This may confuse the real-time system. Therefore, seedlink and other modules
   creating or processing picks should be
   stopped, the seedlink buffer should be cleared and the processing
   modules should be restarted to clear the buffers before starting the
   historic playbacks. Make sure :ref:`scautopick` is configured or started with
   the :option:`--playback` option. Example:

   .. code-block:: sh

      seiscomp stop
      rm -rf $SEISCOMP_ROOT/var/lib/seedlink/buffer
      seiscomp start
      msrtsimul ...


Compressed input files
----------------------

msrtsimul transparently decompresses :file:`.gz` and :file:`.bz2` files.
No extra flags are needed — just pass the compressed file as the argument:

.. code-block:: sh

   msrtsimul event.mseed.gz
   msrtsimul event.mseed.bz2

Decompression happens on-the-fly as records are read, so there is no
additional memory overhead beyond a normal playback.


Sorting unsorted input
----------------------

The input file must be sorted by end_time for correct real-time pacing.
If this requirement cannot be guaranteed, use :option:`--sort` to have
msrtsimul sort the records at startup before playback begins:

.. code-block:: sh

   msrtsimul --sort unsorted.mseed

.. note::

   :option:`--sort` reads the entire file into memory. For large files it is
   more efficient to sort beforehand with :ref:`scmssort`:

   .. code-block:: sh

      scmssort -u -E 'unsorted.mseed' > sorted.mseed
      msrtsimul sorted.mseed


Stream filtering
----------------

The :option:`--filter` option accepts a *NET.STA.LOC.CHA* pattern with wildcards
``*`` and ``?`` and can be specified multiple times. Only streams matching at
least one pattern are injected. This is useful when a miniSEED file contains
many channels but only a subset is needed for a specific test.


Time window selection
---------------------

By default msrtsimul injects the entire file. The playback window can be
narrowed with:

* :option:`--start-time` — skip records with begin time before this UTC timestamp.
  For large skips, :option:`--jump` is more efficient as it avoids waiting through
  the pacing of skipped records.
* :option:`--end-time` — stop when records reach this UTC timestamp.
* :option:`--duration` — limit playback to this many seconds. When combined with
  :option:`--start-time` it sets an absolute end time; otherwise the window starts
  from the first injected record.


Pre-filling the buffer with jumped data
---------------------------------------

By default, :option:`--jump` discards the skipped records entirely. When the
:option:`--inject-jump` flag is also set, the records within the jump window are
instead injected at full speed (no pacing) before the real-time portion begins.
This pre-fills the SeedLink waveform buffer with historical data, which is
required by modules such as :ref:`scautomt` that need a minimum amount of
continuous waveform data (e.g. 12 minutes) before the event origin time.

Example: inject 15 minutes of pre-event data at full speed, then continue in
real time:

.. code-block:: sh

   msrtsimul --jump 15 --inject-jump miniSEED-file


Looping
-------

The :option:`--loop` flag causes msrtsimul to seek back to the beginning of the
file and repeat playback indefinitely after reaching the end. This is not
available when reading from stdin.


seedlink setup
--------------

For supporting msrtsimul activate the :confval:`msrtsimul` parameter in the
seedlink module configuration (:file:`seedlink.cfg`), update the configuration
and restart seedlink before running msrtsimul:

.. code-block:: sh

   seiscomp update-config seedlink
   seiscomp restart seedlink
   msrtsimul ...


Examples
--------

1. Playback miniSEED waveforms in real time with verbose output:

   .. code-block:: sh

      msrtsimul -v miniSEED-file

#. Playback miniSEED waveforms in historic mode. This may require :ref:`scautopick`
   to be started with the option *playback*:

   .. code-block:: sh

      msrtsimul -v -m historic miniSEED-file

#. Feed the data into the buffer of a specific seedlink instance, e.g. *seedlink-test*:

   .. code-block:: sh

      msrtsimul -v --seedlink seedlink-test miniSEED-file

#. Inject only broadband vertical channels from the AU network:

   .. code-block:: sh

      msrtsimul --filter 'AU.*.*.BHZ' miniSEED-file

#. Inject multiple stream patterns at double speed:

   .. code-block:: sh

      msrtsimul -s 2 --filter 'AU.*.*.*' --filter 'IU.CTAO.*.*' miniSEED-file

#. Inject a 10-minute window starting at a specific time:

   .. code-block:: sh

      msrtsimul --start-time 2023-06-01T04:30:00 --duration 600 miniSEED-file

#. Write to an arbitrary named pipe instead of the default seedlink mseedfifo:

   .. code-block:: sh

      msrtsimul --fifo /path/to/custom/mseedfifo miniSEED-file

#. Inject 12 minutes of pre-event data at full speed, then continue in real time
   (required by scautomt for its pre-event waveform buffer):

   .. code-block:: sh

      msrtsimul --jump 12 --inject-jump miniSEED-file

#. Loop a short event file continuously for demonstration purposes:

   .. code-block:: sh

      msrtsimul --loop -v miniSEED-file
