import sp
import socket
import asyncio
import threading
from osc_lib import SPOSC, OSCTypes
from pythonosc.osc_message_builder import OscMessageBuilder
import os

class MADRIXIntegration(sp.BaseModule):
    pluginInfo = {
        "name": "MADRIX Integration",
        "category": "Lighting Control",
        "description": "Control MADRIX lighting software via OSC",
        "author": "STAGE PRECISION",
        "keywords": "madrix, osc, lighting",
        "version": (1, 0),
        "spVersion": (1, 9, 0),
        "helpPath": os.path.join(os.path.dirname(os.path.abspath(__file__)), "help.md"),
        "iconPath": os.path.join(os.path.dirname(os.path.abspath(__file__)), "madrix.svg")
    }

    def __init__(self):
        super().__init__()
        self.osc = None
        self.targetIP = None
        self.targetPort = None
        self.prefixParam = None
        self.listenIP = None
        self.listenPort = None
        self.enableListener = None  

    def afterInit(self):
        try:
            self.targetIP = self.moduleContainer.addIPParameter("Target IP", False)
            self.targetPort = self.moduleContainer.addIntParameter("Target Port", 9001, 1, 65535)
            self.prefixParam = self.moduleContainer.addStringParameter("OSC Prefix", "")
            self.listenIP = self.moduleContainer.addIPParameter("Listen IP", False)
            self.listenPort = self.moduleContainer.addIntParameter("Local Listen Port", 9002, 1, 65535)
            self.enableListener = self.moduleContainer.addBoolParameter("Enable Listener", True)

            self.osc = SPOSC(
                logger=self.log,
                host=self.targetIP.value,
                port=self.targetPort.value,
                prefix=self.prefixParam.value
            )

            self.addAction("Initialize", "Connection", self.initialize_osc)

            # Audio/Input Actions
            self.osc.oscAction(self, "Set Input AGC", "Audio", "Enable or disable Automatic Gain Control", OSCTypes.Bool, # changed to Bool for consistency
                               "/Audio/Input/Agc", "{B, AGC, 0, 0;1, Enable;Disable}")
            self.osc.oscAction(self, "Set Input Level", "Audio", "Set input audio level", OSCTypes.Float,
                               "/Audio/Input/Level", "{F, Level, 50, 0, 100, %}")
            self.osc.oscAction(self, "Set Input Level Offset", "Audio", "Set input level offset", OSCTypes.Float,
                               "/Audio/Input/Level/Offset", "{F, Offset, 0, -100, 100, %}")
            self.osc.oscAction(self, "Mute Input", "Audio", "Mute or unmute input audio", OSCTypes.Bool, #here changed to Bool for consistency
                               "/Audio/Input/Mute", "{B, Mute, 0, 0;1, Off;On}")

            # Audio/Output Actions
            self.osc.oscAction(self, "Set Output Level", "Audio", "Set output audio level", OSCTypes.Float,
                               "/Audio/Output/Level", "{F, Level, 50, 0, 100, %}")
            self.osc.oscAction(self, "Set Output Level Offset", "Audio", "Set output level offset", OSCTypes.Float,
                               "/Audio/Output/Level/Offset", "{F, Offset, 0, -100, 100, %}")
            self.osc.oscAction(self, "Mute Output", "Audio", "Mute or unmute output audio", OSCTypes.Bool, # changed to Bool for consistency
                               "/Audio/Output/Mute", "{B, Mute, 0, 0;1, Off;On}")

            # Output Actions
            self.osc.oscAction(self, "Freeze Output", "Output", "Freeze or unfreeze output", OSCTypes.Bool, # changed to Bool for consistency
                               "/Output/Freeze", "{B, Freeze, 0, 0;1, Off;On}")
            self.osc.oscAction(self, "Set Master Level", "Output", "Set master intensity", OSCTypes.Int,
                               "/Output/Master", "{I, Level, 127, 0, 255}")
            self.osc.oscAction(self, "Set Master Offset", "Output", "Set master level offset", OSCTypes.Float,
                               "/Output/Master/Offset", "{F, Offset, 0, -100, 100, %}")
            self.osc.oscAction(self, "Blackout", "Output", "Enable or disable blackout", OSCTypes.Bool, # changed to Bool for consistency
                               "/Output/Blackout", "{B, Blackout, 0, 0;1, Off;On}")

            # CueList Actions
            self.osc.oscAction(self, "Set CueList Index", "CueList", "Set cue list index", OSCTypes.Int,
                               "/CueList/Index", "{I, Index, 0, 0, 999}")
            self.osc.oscAction(self, "Next CueList", "CueList", "Move to next cue list", OSCTypes.Bare,
                               "/CueList/Index/Up")
            self.osc.oscAction(self, "Previous CueList", "CueList", "Move to previous cue list", OSCTypes.Bare,
                               "/CueList/Index/Down")
            self.osc.oscAction(self, "Set Playback Mode (LOOP/SHUFFLE)", "CueList", "Set playback mode", OSCTypes.Bool,# playback mode
                               "/CueList/PlaybackMode", "{B, Mode, 0, 0;1, Loop;Shuffle}")      

            self.osc.oscAction(self, "Set Playback State (0-STOP, 1-PAUSE, 2-PLAY)", "CueList", "Set playback state",
                               OSCTypes.Bare, "/CueList/PlaybackState/{I, State, 0, 0, 2}")
            self.osc.oscAction(self, "Set Timecode Source", "CueList", "Set timecode source", OSCTypes.String,
                        "/CueList/TimeCodeSource", "{S, Source, SMPTE, None;Art-net;MIDI;SMPTE;System Time}") 
            self.osc.oscAction(self, "Next Timecode Source", "CueList", "Move to next timecode source", OSCTypes.Bare,
                               "/CueList/TimeCodeSource/Up")
            self.osc.oscAction(self, "Previous Timecode Source", "CueList", "Move to previous timecode source", OSCTypes.Bare,
                               "/CueList/TimeCodeSource/Down")

            # Cues Actions
            self.osc.oscAction(self, "Set Cue Index", "Cues", "Set cue index", OSCTypes.Int,
                               "/Cues/Index", "{I, Index, 0, 0, 999}")
            self.osc.oscAction(self, "Next Cue", "Cues", "Move to next cue", OSCTypes.Bare,
                               "/Cues/Index/Up")
            self.osc.oscAction(self, "Previous Cue", "Cues", "Move to previous cue", OSCTypes.Bare,
                               "/Cues/Index/Down")

            self.setup_feedback()
            self.onEnabling()
        except Exception as e:
            self.logError(f"afterInit: Failed to initialize plugin: {e}")
            self.setStatus(sp.StatusType.ConnectionError, f"Initialization failed: {str(e)}")

    def initialize_osc(self, callback):
        try:
            if not self.targetIP.value or not self.targetPort.value:
                self.setStatus(sp.StatusType.InvalidSettings, "Target IP or Port is invalid")
                callback(False)
                return
            self.osc.update_config(self.targetIP.value, self.targetPort.value, self.prefixParam.value)
            self.setStatus(sp.StatusType.Active, f"Configured to {self.targetIP.value}:{self.targetPort.value}")
            callback(True)
        except Exception as e:
            self.logError(f"[Initialize OSC] Failed: {e}")
            self.setStatus(sp.StatusType.ConnectionError, "Initialization failed")
            callback(False)

    def onEnabling(self):
        self.initialize_osc(lambda _: "")
        self.setStatus(sp.StatusType.Connected, "Sender Connected")
        try:
            self.osc.update_config(self.targetIP.value, self.targetPort.value, self.prefixParam.value)
            if self.enableListener.value:
                self.osc.enable(
                    listen_ip=self.listenIP.value,
                    listen_port=self.listenPort.value,
                    retry_interval=5
                )
        except Exception as e:
            self.setStatus(sp.StatusType.InvalidSettings, f"Listener failed: {str(e)}")

    def onDisabling(self):
        self.setStatus(sp.StatusType.Disabled, "Plugin disabled")
        if self.enableListener.value:
            self.osc.disable()

    def shutdown(self):
        self.setStatus(sp.StatusType.Disconnect, "Plugin stopped")
        if self.enableListener.value:
            self.osc.disable()

    def onParameterFeedback(self, param):
        if param in (self.targetIP, self.targetPort, self.prefixParam):
            if self.targetIP.value and self.targetPort.value:
                self.osc.update_config(self.targetIP.value, self.targetPort.value, self.prefixParam.value)
        if self.enableListener.value and param in (self.listenIP, self.listenPort):
            self.osc.restart(
                listen_ip=self.listenIP.value,
                listen_port=self.listenPort.value,
                retry_interval=5
            )

    def setup_feedback(self): 
        self.osc.oscEntityReceiver(self, "Input Level Feedback", OSCTypes.Float, "/Audio/Input/Level", "Status/InputLevel")
        self.osc.oscEntityReceiver(self, "Output Level Feedback", OSCTypes.Float, "/Audio/Output/Level", "Status/OutputLevel")
        self.osc.oscEntityReceiver(self, "Master Level Feedback", OSCTypes.Int, "/Output/Master", "Status/MasterLevel")
        self.osc.oscEntityReceiver(self, "Playback State Feedback", OSCTypes.Int, "/CueList/PlaybackState", "Status/PlaybackState")
        self.osc.oscEntityReceiver(self, "Playback Mode Feedback", OSCTypes.Int, "/CueList/PlaybackMode", "Status/PlaybackMode")
        self.osc.oscEntityReceiver(self, "Timecode Source Feedback", OSCTypes.Int, "/CueList/TimeCodeSource", "Status/TimeCodeSource")

if __name__ == "__main__":
    sp.registerPlugin(MADRIXIntegration)