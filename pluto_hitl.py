#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: SDCS Digital Twin — Pluto HITL
# Author: SDCS Digital Twin Team
# Description: Hardware In The Loop Pluto SDR Transceiver Bridge for SDCS Digital Twin
# GNU Radio version: 3.10.12.0

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import iio
from gnuradio import zeromq
from xmlrpc.server import SimpleXMLRPCServer
import threading



class pluto_hitl(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "SDCS Digital Twin — Pluto HITL", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("SDCS Digital Twin — Pluto HITL")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("gnuradio/flowgraphs", "pluto_hitl")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.tx_atten = tx_atten = 30
        self.samp_rate = samp_rate = 1000000
        self.rx_gain = rx_gain = 40
        self.rf_bw = rf_bw = 1500000
        self.pluto_uri = pluto_uri = iio.get_pluto_uri()
        self.center_freq = center_freq = 2400000000

        ##################################################
        # Blocks
        ##################################################

        self.zeromq_push_sink_0 = zeromq.push_sink(gr.sizeof_gr_complex, 1, 'tcp://127.0.0.1:5555', 100, False, (-1), False)
        self.zeromq_pull_source_0 = zeromq.pull_source(gr.sizeof_gr_complex, 1, 'tcp://127.0.0.1:5556', -1, False, (-1), False)
        self.xmlrpc_server_0 = SimpleXMLRPCServer(('127.0.0.1', 8090), allow_none=True)
        self.xmlrpc_server_0.register_instance(self)
        self.xmlrpc_server_0_thread = threading.Thread(target=self.xmlrpc_server_0.serve_forever)
        self.xmlrpc_server_0_thread.daemon = True
        self.xmlrpc_server_0_thread.start()
        self.iio_pluto_source_0 = iio.fmcomms2_source_fc32(pluto_uri if pluto_uri else iio.get_pluto_uri(), [True, True], 8192)
        self.iio_pluto_source_0.set_len_tag_key('')
        self.iio_pluto_source_0.set_frequency(center_freq)
        self.iio_pluto_source_0.set_samplerate(samp_rate)
        self.iio_pluto_source_0.set_gain_mode(0, 'manual')
        self.iio_pluto_source_0.set_gain(0, rx_gain)
        self.iio_pluto_source_0.set_quadrature(True)
        self.iio_pluto_source_0.set_rfdc(True)
        self.iio_pluto_source_0.set_bbdc(True)
        self.iio_pluto_source_0.set_filter_params('Auto', '', 0, 0)
        self.iio_pluto_sink_0 = iio.fmcomms2_sink_fc32(pluto_uri if pluto_uri else iio.get_pluto_uri(), [True, True], 8192, False)
        self.iio_pluto_sink_0.set_len_tag_key('')
        self.iio_pluto_sink_0.set_bandwidth(rf_bw)
        self.iio_pluto_sink_0.set_frequency(center_freq)
        self.iio_pluto_sink_0.set_samplerate(samp_rate)
        self.iio_pluto_sink_0.set_attenuation(0, tx_atten)
        self.iio_pluto_sink_0.set_filter_params('Auto', '', 0, 0)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.iio_pluto_source_0, 0), (self.zeromq_push_sink_0, 0))
        self.connect((self.zeromq_pull_source_0, 0), (self.iio_pluto_sink_0, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "pluto_hitl")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_tx_atten(self):
        return self.tx_atten

    def set_tx_atten(self, tx_atten):
        self.tx_atten = tx_atten
        self.iio_pluto_sink_0.set_attenuation(0,self.tx_atten)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.iio_pluto_sink_0.set_samplerate(self.samp_rate)
        self.iio_pluto_source_0.set_samplerate(self.samp_rate)

    def get_rx_gain(self):
        return self.rx_gain

    def set_rx_gain(self, rx_gain):
        self.rx_gain = rx_gain
        self.iio_pluto_source_0.set_gain(0, self.rx_gain)

    def get_rf_bw(self):
        return self.rf_bw

    def set_rf_bw(self, rf_bw):
        self.rf_bw = rf_bw
        self.iio_pluto_sink_0.set_bandwidth(self.rf_bw)

    def get_pluto_uri(self):
        return self.pluto_uri

    def set_pluto_uri(self, pluto_uri):
        self.pluto_uri = pluto_uri

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.iio_pluto_sink_0.set_frequency(self.center_freq)
        self.iio_pluto_source_0.set_frequency(self.center_freq)




def main(top_block_cls=pluto_hitl, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()
    tb.flowgraph_started.set()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
