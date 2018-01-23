#! /usr/bin/env python3
# -*- coding: utf-8 -*-

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


__version__ = '0.02'


"""
version
0.02 pour présentation
0.01 blendcontrol
"""


import os
# Bidouille pour que python trouve java sur mon PC
##os.environ["JAVA_HOME"] = "/usr/lib/jvm/java-8-openjdk-amd64"

from time import time
import socket
import json
import ast

import kivy
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.properties import NumericProperty, ObjectProperty
from kivy.properties import StringProperty
from kivy.core.window import Window
from kivy.config import Config
from kivy.clock import Clock

# Le fichier de ce module est dans le dossier courant
from labtcpclient import LabTcpClient
from labmulticast import Multicast


def get_my_LAN_ip():
    """Récupère mon ip sur Android"""

    sok = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sok.connect(("8.8.8.8", 80))
    ip = sok.getsockname()[0]
    sok.close()

    return ip

def xy_correction(x, y):
    """Retourne x, y recalcule au dessus du bouton, de 0 a 1."""

    a1 = 0.015
    a2 = 0.50
    b1 = 0.09
    b2 = 0.97

    if x <= a1:
        x = 0.0
    elif x >= a2:
        x = 1.0
        y = None
    elif a1 < x < a2:
        x = (x / (a2 - a1)) - a1 / (a2- a1)

    if y:
        if y <= b1:
            y = 0.0
        elif y >= b2:
            y = 1.0
        elif b1 < y < b2:
            y = (y / (b2 - b1)) - b1 / (b2- b1)

    return x, y

def test_old_new_acc(acc_old, acc_new):
    """acc = liste de 3
    arrondi à 0.01
    retourne True si différent, False sinon
    les capteurs sont imprécis et instable, retourne toujours True
    fréquence maxi définie dans les options
    """

    ret = False
    if isinstance(acc_old, list) and len(acc_old) == 3:
        if isinstance(acc_new, list) and len(acc_new) == 3:
            # Arrondi a 0.01
            a_old = [int(100 * acc_old[0]),
                     int(100 * acc_old[1]),
                     int(100 * acc_old[2])]
            a_new = [int(100 * acc_new[0]),
                     int(100 * acc_new[1]),
                     int(100 * acc_new[2])]
            if a_old != a_new:
                ret = True
            else:
                print("Pas de changement des Accélérations à 0.01 près")
    return ret

def test_old_new_xy(xy_old, xy_new):
    """xy = liste de 2, arrondi à 0.01 """

    ret = False

    if xy_new[0] != None and xy_new[1] != None:
        if isinstance(xy_old, list) and len(xy_old) == 2:
            if isinstance(xy_new, list) and len(xy_new) == 2:
                # Arrondi a 0.01
                a_old = [int(100 * xy_old[0]), int(100 * xy_old[1])]
                a_new = [int(100 * xy_new[0]), int(100 * xy_new[1])]
                if a_old != a_new:
                    ret = True

    return ret

def datagram_to_dict(data):
    """Décode le message. Retourne un dict ou None."""

    try:
        dec = data.decode("utf-8")
    except:
        print("Décodage UTF-8 impossible")
        dec = data

    try:
        msg = ast.literal_eval(dec)
    except:
        print("ast.literal_eval impossible")
        msg = dec

    if isinstance(msg, dict):
        return msg
    else:
        print("Message reçu: None")
        return None


class Network:
    """Message recu du serveur:
        {'svr_msg': {   'ip': '192.168.1.12',
                        'dictat': {à voir}}}

        Message envoyé:
        {"xy": [0.135, 0.358]}
    """

    def __init__(self, screen_manager):

        # config, obtenu avec des dir()
        self.config = BlendControlApp.get_running_app().config

        self.t_print = time()

        # Multi
        self.create_multicast_receiver()

        # Serveur data
        self.info = None

        # TCP
        self.tcp_ip = None
        self.tcp_port = self.get_tcp_port()
        self.tcp_clt = None
        self.tcp_msg = {}

        print("Initialisation de Network ok")

    def network_update(self):
        """Maj de réception, maj des datas, envoi"""

        # Recup du message du serveur en multicast
        svr_msg = self.get_multicast_msg()
        self.get_info(svr_msg)

        # Set TCP
        if not self.tcp_ip:
            self.tcp_ip = self.get_server_ip(svr_msg)
        self.create_tcp_socket()

    def create_multicast_receiver(self):
        self.multi_ip, self.multi_port = self.get_multicast_addr()
        self.my_multi = Multicast(  self.multi_ip,
                                    self.multi_port,
                                    1024)

        print("Réception Mlticast créée:", self.my_multi)

    def get_multicast_addr(self):
        """Retourne l'adresse multicast"""

        multi_ip = self.config.get('network', 'multi_ip')
        multi_port = int(self.config.get('network', 'multi_port'))

        return multi_ip, multi_port

    def get_multicast_msg(self):
        """Error si pas de data à lire:
        freq envoi du serveur = 1
        freq lecture ici = 30 à 60
        {"svr_msg": {"ip": self.ip_server, "info": self.info}}
        """

        try:
            data = self.my_multi.receive()
            svr_msg = datagram_to_dict(data)
        except:
            svr_msg = None

        return svr_msg

    def get_info(self, svr_msg):
        """Retourne info"""

        try:
            sm = svr_msg["svr_msg"]
            self.info = sm["info"]
        except:
            pass

    def get_server_ip(self, svr_msg):

        try:
            tcp_ip = svr_msg["svr_msg"]["ip"]
            print("IP du server:", tcp_ip)
        except:
            tcp_ip = None

        return tcp_ip

    def get_tcp_port(self):
        """Retourne le port TCP"""

        return int(self.config.get('network', 'tcp_port'))

    def create_tcp_socket(self):
        if self.tcp_ip and not self.tcp_clt:
            try:
                self.tcp_clt = LabTcpClient(self.tcp_ip,
                                            self.tcp_port)
                print("Client TCP créé")
            except:
                self.tcp_clt = None
                print("Pas d'ip dans le message du serveur")

    def send_tcp_msg(self, msg):
        if msg:
            env = json.dumps(msg).encode("utf-8")
            if self.tcp_clt:
                print("Envoi de:", env)
                self.tcp_clt.send(env)


class Game(Network):

    def __init__(self, screen_manager, **kwargs):

        super(Game, self).__init__(screen_manager, **kwargs)

        self.scr_manager = screen_manager
        self.cur_screen = self.get_current_screen()

        # Vérif freq
        self.t = time()
        self.v_freq = 0

        # Lancement de la boucle de jeu
        self.start()

        print("Initialisation de Game ok")

    def start(self):
        """Rafraichissement du jeu"""

        self.tempo = self.get_tempo()

        Clock.unschedule(self.game_update)
        self.event = Clock.schedule_interval(self.game_update,
                                             self.tempo)

    def get_tempo(self):
        """Retourne la tempo pour la boucle de Clock."""

        config = BlendControlApp.get_running_app().config
        freq = int(config.get('network', 'freq'))

        if freq > 60:
            freq = 60
        if freq < 1:
            freq = 1
        print("Frequence d'envoi en TCP =", freq)
        return 1/freq

    def game_update(self, dt):

        self.verif_freq()
        self.network_update()

        # Maj du screen courant
        self.get_current_screen()

        # Envoi au serveur
        self.create_msg()
        self.send_tcp_msg(self.tcp_msg)
        self.reset_tcp_msg()

        # Affichage info
        self.display_info()

    def verif_freq(self):
        self.v_freq += 1
        a = time()
        if a - self.t > 1:
            #print("FPS:", self.v_freq)
            self.v_freq = 0
            self.t = a

    def get_current_screen(self):
        """Retourne le screen en cours"""

        self.cur_screen = self.scr_manager.current_screen

    def create_msg(self):
        if "Menu" not in self.cur_screen.name:
            self.tcp_msg = self.get_tcp_msg()
        else:
            self.tcp_msg = None

    def get_tcp_msg(self):
        """Valable pour tous les écrans"""

        return self.cur_screen.get_tcp_msg()

    def reset_tcp_msg(self):
        """Valable pour tous les écrans"""

        if "Menu" not in self.cur_screen.name:
            self.cur_screen.reset_tcp_msg()

    def display_info(self):
        """Valable pour tous les écrans"""

        if "Menu" not in self.cur_screen.name:
            self.cur_screen.set_info(self.info)


class Menu(Screen):

    def __init__(self, **kwargs):
        super(Menu, self).__init__(**kwargs)

        # Construit le jeu, le réseau, tourne tout le temps
        scr_manager = self.get_screen_manager()
        self.game = Game(scr_manager)

        print("Main Screen init ok")

    def get_screen_manager(self):
        return BlendControlApp.get_running_app().screen_manager


class Screen1(Screen):

    info = StringProperty()

    def __init__(self, **kwargs):

        super(Screen1, self).__init__(**kwargs)

        self.tcp_msg = None

        # Info from server : set with info from server
        self.info = "Retour d'info"

        self.xy_old = [0, 0]

        print("Screen1 init ok")

    def set_info(self, stuff):
        """self.info is used to display info in every Sceen."""

        self.info = str(stuff)

    def on_touch_move(self, touch):
        """Si move sur l'écran, n'importe où."""

        x = touch.spos[0]
        y = touch.spos[1]
        self.apply_on_touch(x, y)

    def apply_on_touch(self, x, y):
        """Envoie la position du curseur."""

        xy_new = [x, y]
        # Pas de None
        if x and y:
            # Si valeurs différentes à 0.01 près
            if test_old_new_xy(self.xy_old, xy_new):
                self.tcp_msg = {"screen 1": {"xy": xy_new}}

    def get_tcp_msg(self):
        return self.tcp_msg

    def reset_tcp_msg(self):
        self.tcp_msg = None


class Screen2(Screen):

    info = StringProperty()

    def __init__(self, **kwargs):

        super(Screen2, self).__init__(**kwargs)

        self.tcp_msg = None

        # Info from server : set with info from server
        self.info = "Retour d'info"

        print("Screen2 init ok")

    def set_info(self, stuff):
        """self.info is used to display info in every Sceen."""

        self.info = str(stuff)

    def on_state(self, iD, state):

        print("Button {} {}".format(iD, state))
        
        if state == "down":
            self.tcp_msg = {"screen 2": {"button": {iD: 1}}}
        else:
            self.tcp_msg = {"screen 2": {"button": {iD: 0}}}
        
    def do_slider(self, iD, instance, value):
        """Appelé si slider change."""

        print("Slider value {} = {}".format(iD, value))

        self.tcp_msg = {"screen 2": {"slider": {iD: value}}}

    def get_tcp_msg(self):
        return self.tcp_msg

    def reset_tcp_msg(self):
        self.tcp_msg = None


class Screen3(Screen):

    info = StringProperty()

    def __init__(self, **kwargs):

        super(Screen3, self).__init__(**kwargs)

        self.tcp_msg = None

        self.xy_old = [0, 0]

        # Info from server : set with info from server
        self.info = "Retour d'info"

        print("Screen3 init ok")

    def set_info(self, stuff):
        """self.info is used to display info in every Sceen."""

        self.info = str(stuff)

    def on_touch_move(self, touch):
        """Si move sur l'ecran, n'import ou."""

        x = touch.spos[0]
        y = touch.spos[1]
        self.apply_on_touch(x, y)

    def apply_on_touch(self, x, y):
        """Envoi la position du curseur. Non applique si slider"""

        xy_cor = xy_correction(x, y)
        xy_new = [xy_cor[0], xy_cor[1]]

        # Pas de None
        if x and y:
            if test_old_new_xy(self.xy_old, xy_new):
                print("Position x={} y={}".format(x, y))
                self.tcp_msg = {"screen 3": {"xy": xy_new}}

    def do_slider(self, iD, instance, value):
        """Appelé si slider change."""

        print("slider", iD, value)
        self.tcp_msg = {"screen 3": {"slider": {iD: value}}}

    def get_tcp_msg(self):
        return self.tcp_msg

    def reset_tcp_msg(self):
        self.tcp_msg = None


# Liste des écrans, cette variable appelle les classes ci-dessus
# et doit être placée après ces classes
SCREENS = { 0: (Menu,    "Menu"),
            1: (Screen1, "Ecran 1"),
            2: (Screen2, "Ecran 2"),
            3: (Screen3, "Ecran 3")}


class BlendControlApp(App):
    """Excécuté par __main__,
    app est le parent de cette classe dans kv.
    """

    def build(self):
        """Exécuté en premier après run()"""

        # Creation des ecrans
        self.screen_manager = ScreenManager()
        for i in range(len(SCREENS)):
            self.screen_manager.add_widget(SCREENS[i][0](name=SCREENS[i][1]))

        return self.screen_manager

    def build_config(self, config):
        """Si le fichier *.ini n'existe pas,
        il est créé avec ces valeurs par défaut.
        Si il manque seulement des lignes, il ne fait rien !
        """

        config.setdefaults('network',
                            { 'multi_ip': '228.0.0.5',
                              'multi_port': '18888',
                              'tcp_port': '8000',
                              'freq': '60'})

        config.setdefaults('kivy',
                            { 'log_level': 'debug',
                              'log_name': 'sendjson_%y-%m-%d_%_.txt',
                              'log_dir': '/sdcard',
                              'log_enable': '1'})

        config.setdefaults('postproc',
                            { 'double_tap_time': 250,
                              'double_tap_distance': 20})

    def build_settings(self, settings):
        """
        Construit l'interface de l'écran Options,
        pour sendjson seul,
        Kivy est par défaut,
        appelé par app.open_settings() dans .kv
        """

        # TODO vérifier la cohérence des ip, port
        data = """[{"type": "title", "title":"Configuration du réseau"},
                      {"type": "numeric",
                      "title": "Fréquence",
                      "desc": "Fréquence entre 1 et 60 Hz",
                      "section": "network", "key": "freq"},

                      {"type": "numeric",
                      "title": "IP Multicast pour la réception",
                      "desc": "Exemple: 228.0.0.5",
                      "section": "network", "key": "multi_ip"},

                      {"type": "numeric",
                      "title": "Port Multicast pour la réception",
                      "desc": "Exemple 18888",
                      "section": "network", "key": "multi_port"},

                      {"type": "numeric",
                      "title": "Port TCP pour l'envoi",
                      "desc": "Fréquence entre 1 et 60 Hz",
                      "section": "network", "key": "tcp_port"}

                   ]"""

        # self.config est le config de build_config
        settings.add_json_panel('BlendControl', self.config, data=data)

    def on_config_change(self, config, section, key, value):
        """Si modification des options, fonction appelée
        automatiquement.
        """

        menu = self.screen_manager.get_screen("Menu")

        if config is self.config:
            token = (section, key)

            if token == ('network', 'freq'):
                # Set sleep in loop
                menu.game.start()

        if section == 'graphics' and key == 'rotation':
            Config.set('graphics', 'rotation', int(value))
            print("Screen rotation = {}".format(value))

    def go_mainscreen(self):
        """Retour au menu principal depuis les autres ecrans."""

        #if touch.is_double_tap:
        self.screen_manager.current = ("Menu")

    def do_quit(self):
        """Quit propre, stop le client, le serveur."""

        # Accés à screen manager dans BlendControlApp
        screen_manager = BlendControlApp.get_running_app().screen_manager
        # Accés à l'écran Menu
        menu = screen_manager.get_screen("Menu")

        print("Quit in BlendControlApp(App)")

        # Kivy
        BlendControlApp.get_running_app().stop()

        # Fin
        os._exit(0)


if __name__ == '__main__':
    BlendControlApp().run()
    print("Le petit chaperon rouge")
