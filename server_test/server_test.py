#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

#  server_test.py

# #####################################################################
# Copyright (C) La Labomedia January 2018
#
# This file is part of blendcontrol.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
# #####################################################################

"""
Envoi en multicast sur 
ip = "228.0.0.5"
port = 18888

Ecoute le TCP
port = 8000

"""



import os, sys
from time import time, sleep
import threading
import json
import ast

from twisted.internet.protocol import DatagramProtocol
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor

from mylabotools.labconfig import MyConfig
from mylabotools.labsometools import get_my_ip
from mylabotools.mytools import MyTools



# Variable globale
scr = os.path.dirname(os.path.abspath(__file__))
conf = MyConfig(scr + "/server_test.ini")
my_conf = conf.conf
print("Configuration du serveur: {}\n".format(my_conf))

MULTICAST_IP = my_conf["multicast"]["ip"]
MULTICAST_PORT = my_conf["multicast"]["port"]
MULTICAST_FREQ = my_conf["multicast"]["freq"]
TCP_PORT = my_conf["tcp"]["port"]
print(MULTICAST_IP, MULTICAST_PORT, MULTICAST_FREQ, TCP_PORT)


class MyMulticastSender(DatagramProtocol):
    """Envoi en continu à 60 fps à tous les joueurs, ip et data."""

    def __init__(self):

        self.tempo = time()
        self.count = 0
        self.ip_server = get_my_ip()
        
        # pour retour sur android
        self.info = 0

        print("Envoi en multicast sur", MULTICAST_IP,
                                        MULTICAST_PORT, "\n")

    def startProtocol(self):
        """Called after protocol has started listening."""

        # Set the TTL>1 so multicast will cross router hops:
        # https://www.rap.prd.fr/pdf/technologie_multicast.pdf

        # préconise TTL = 1
        self.transport.setTTL(2)

        # Join a specific multicast group:
        self.transport.joinGroup(MULTICAST_IP)

        # Boucle infinie pour envoi continu à tous les joueurs
        self.send_loop_thread()

    def create_multi_msg(self):
        """Retourne msg encodé à envoyer en permanence, dès __init__"""

        lapin = {"svr_msg": {"ip": self.ip_server, "info": self.info}}

        lapin_enc = json.dumps(lapin).encode("utf-8")

        return lapin_enc

    def send_loop(self):
        """Envoi de l'IP en permanence."""

        addr = MULTICAST_IP, MULTICAST_PORT

        while 1:
            sleep(MULTICAST_FREQ)
            # envoi
            lapin = self.create_multi_msg()
            try:
                self.transport.write(lapin, addr)
                self.info += 1
            except OSError as e:
                print("OSError", e)
                if e.errno == 101:
                    print("Network is unreachable")

    def send_loop_thread(self):
        thread_s = threading.Thread(target=self.send_loop)
        thread_s.start()


class MyTcpServer(Protocol):
    """Reception de chaque joueur en TCP."""

    def __init__(self, factory):
        self.factory = factory

        # Permet de distinguer les instances des joueurs et de blender
        self.create_user()

        self.tempo = time()

    def create_user(self):
        """Impossible d'avoir 2 user identiques"""

        self.user = "TCP" + str(int(10000* time()))[-8:]
        print("Un user créé: ", self.user)

    def connectionMade(self):
        self.addr = self.transport.client
        print("Une connexion établie par le client {}".format(self.addr))

    def connectionLost(self, reason):
        print("Connection lost, reason:", reason)
        print("Connexion fermée avec le client {}".format(self.addr))

    def dataReceived(self, data):

        # Retourne un dict ou None
        data = datagram_to_dict(data)
        print("data", data)


class MyTcpServerFactory(Factory):
    """self ici sera self.factory dans les objets MyTcpServer."""

    def __init__(self):

        # Serveur
        self.numProtocols = 1
        print("Serveur twisted réception TCP sur {}\n".format(TCP_PORT))

    def buildProtocol(self, addr):
        print("Nombre de protocol dans factory", self.numProtocols)

        # le self permet l'accès à self.factory dans MyTcpServer
        return MyTcpServer(self)


def datagram_to_dict(data):
    """Decode le message.
    Retourne un dict ou None
    """

    try:
        dec = data.decode("utf-8")
    except:
        #print("Décodage UTF-8 impossible")
        dec = data

    try:
        msg = ast.literal_eval(dec)
    except:
        #print("ast.literal_eval impossible")
        msg = dec

    if isinstance(msg, dict):
        return msg
    else:
        #print("Message reçu: None")
        return None


if __name__ == "__main__":
    ## Receive
    endpoint = TCP4ServerEndpoint(reactor, TCP_PORT)
    endpoint.listen(MyTcpServerFactory())

    ## Send: je reçois aussi ce que j'envoie
    reactor.listenMulticast(MULTICAST_PORT, MyMulticastSender(), listenMultiple=True)

    ## Pour les 2
    reactor.run()
