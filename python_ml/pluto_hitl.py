#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless GNU Radio Transceiver Bridge for Pluto SDR & SDCS Digital Twin.
Transfers complex baseband IQ via ZeroMQ and provides XML-RPC control on port 8090.
"""

import sys
import signal
import time
import threading
from xmlrpc.server import SimpleXMLRPCServer

from gnuradio import gr
from gnuradio import iio
from gnuradio import zeromq

class PlutoHitlHeadless(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "SDCS Digital Twin — Pluto HITL Headless Proxy", catch_exceptions=True)
        
        # Variables
        self.samp_rate = 1000000
        self.center_freq = 2400000000
        self.tx_atten = 30.0
        self.rx_gain = 40.0
        self.rf_bw = 1500000

        # ZMQ PULL Source (Receives complex baseband + 150 kHz Digital IF from Python twin)
        self.zeromq_pull_source_0 = zeromq.pull_source(
            gr.sizeof_gr_complex, 1, 'tcp://127.0.0.1:5556', -1, False, -1, False
        )
        
        # Pluto RF Sink (Transmitter)
        self.iio_pluto_sink_0 = iio.fmcomms2_sink_fc32('ip:192.168.2.1', [True, False], 8192, False)
        self.iio_pluto_sink_0.set_bandwidth(self.rf_bw)
        self.iio_pluto_sink_0.set_frequency(self.center_freq)
        self.iio_pluto_sink_0.set_samplerate(self.samp_rate)
        self.iio_pluto_sink_0.set_attenuation(0, self.tx_atten)
        self.iio_pluto_sink_0.set_filter_params('Auto', '', 0, 0)
        
        # Pluto RF Source (Receiver - matching LO to TX)
        self.iio_pluto_source_0 = iio.fmcomms2_source_fc32('ip:192.168.2.1', [True, False], 8192)
        self.iio_pluto_source_0.set_frequency(self.center_freq)
        self.iio_pluto_source_0.set_samplerate(self.samp_rate)
        self.iio_pluto_source_0.set_gain_mode(0, 'manual')
        self.iio_pluto_source_0.set_gain(0, self.rx_gain)
        self.iio_pluto_source_0.set_quadrature(True)
        self.iio_pluto_source_0.set_rfdc(True)
        self.iio_pluto_source_0.set_bbdc(True)
        self.iio_pluto_source_0.set_filter_params('Auto', '', 0, 0)
        
        # ZMQ PUSH Sink (Transfers full complex IQ baseband to Python backend)
        self.zeromq_push_sink_0 = zeromq.push_sink(
            gr.sizeof_gr_complex, 1, 'tcp://127.0.0.1:5555', 100, False, -1, False
        )

        # Direct complex connections: Python Twin -> Pluto TX -> [AIR] -> Pluto RX -> Python Twin
        self.connect((self.zeromq_pull_source_0, 0), (self.iio_pluto_sink_0, 0))
        self.connect((self.iio_pluto_source_0, 0), (self.zeromq_push_sink_0, 0))

    # XML-RPC Setters
    def set_center_freq(self, freq):
        self.center_freq = int(freq)
        self.iio_pluto_sink_0.set_frequency(self.center_freq)
        self.iio_pluto_source_0.set_frequency(self.center_freq)
        return True

    def set_tx_atten(self, atten):
        self.tx_atten = float(atten)
        self.iio_pluto_sink_0.set_attenuation(0, self.tx_atten)
        return True

    def set_rx_gain(self, gain):
        self.rx_gain = float(gain)
        self.iio_pluto_source_0.set_gain(0, self.rx_gain)
        return True

    def set_samp_rate(self, rate):
        self.samp_rate = int(rate)
        self.iio_pluto_sink_0.set_samplerate(self.samp_rate)
        self.iio_pluto_source_0.set_samplerate(self.samp_rate)
        return True

    def set_rf_bw(self, bw):
        self.rf_bw = int(bw)
        self.iio_pluto_sink_0.set_bandwidth(self.rf_bw)
        return True

def start_xmlrpc_server(tb, host="127.0.0.1", port=8090):
    server = SimpleXMLRPCServer((host, port), allow_none=True, logRequests=False)
    server.register_function(tb.set_center_freq, "set_center_freq")
    server.register_function(tb.set_tx_atten, "set_tx_atten")
    server.register_function(tb.set_rx_gain, "set_rx_gain")
    server.register_function(tb.set_samp_rate, "set_samp_rate")
    server.register_function(tb.set_rf_bw, "set_rf_bw")
    
    server_thread = threading.Thread(target=server.serve_forever, daemon=True, name="PlutoXMLRPC")
    server_thread.start()
    return server

def main():
    print("==================================================")
    print("   Starting Headless Pluto HITL Proxy             ")
    print("   ZMQ Sinks: :5556 (PULL) -> :5555 (PUSH)        ")
    print("   XML-RPC Server: http://127.0.0.1:8090          ")
    print("==================================================")
    
    tb = PlutoHitlHeadless()
    server = start_xmlrpc_server(tb)
    tb.start()
    
    def sig_handler(sig=None, frame=None):
        print("\nShutting down Pluto HITL...")
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        sig_handler()

if __name__ == '__main__':
    main()
