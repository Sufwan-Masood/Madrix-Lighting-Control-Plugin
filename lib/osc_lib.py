import socket
from enum import Enum
import re
from pythonosc.osc_message_builder import OscMessageBuilder
import asyncio
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
import threading
import time


class OSCTypes(Enum):
    Int = "i"
    Float = "f"
    String = "s"
    Blob = "b"
    BigInt = "h"
    TimeTag = "t"
    Double = "d"
    Char = "c"
    Color = "r"
    Midi = "m"
    TrueBit = "T"
    FalseBit = "F"
    Bool = "B"
    Nil = "N"
    Infinitum = "I"
    Bare = ""
    Mixed = "M"



class SPOSC:
    def __init__(self, logger, host, port, prefix=""):
        self.log = logger
        self.host = host
        self.port = port
        self.prefix = prefix

        self._dispatcher = Dispatcher()
        self._osc_server = None
        self._transport = None

        self._listener_enabled = False
        self._loop = None
        self._thread = None

        self._should_run = False  # lifecycle guard

    def enable(self, listen_ip="127.0.0.1", listen_port=9000, retry_interval=5):
        if self._should_run:
            self.log("[SPOSC] Already enabled.")
            return

        self._should_run = True

        def _start_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.create_task(self._main_loop(listen_ip, listen_port, retry_interval))
            self._loop.run_forever()

        self._thread = threading.Thread(target=_start_loop, daemon=True)
        self._thread.start()
        self.log("[SPOSC] Enable: background loop started.")

    def disable(self):
        if not self._should_run:
            self.log("[SPOSC] Already disabled.")
            return

        self._should_run = False
        shutdown_complete = threading.Event()

        async def _shutdown():
            try:
                if self._transport:
                    self._transport.close()
                    self._transport = None
                    self.log("[SPOSC] Transport closed.")

                self._osc_server = None
                self._listener_enabled = False
                self.log("[SPOSC] Server reference cleared.")
            except Exception as e:
                self.log(f"[SPOSC] Error during shutdown: {e}")
            finally:
                shutdown_complete.set()
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)

        shutdown_complete.wait(timeout=2.0)

        if self._thread:
            self._thread.join(timeout=2.0)
            self.log("[SPOSC] Background thread terminated.")

        self._loop = None
        self._thread = None

    async def _main_loop(self, listen_ip, listen_port, retry_interval):
        while self._should_run:
            try:
                if not self._listener_enabled:
                    self.log("[SPOSC] Attempting listener startup...")
                    await self._start_listener(listen_ip, listen_port)
            except Exception as e:
                self.log(f"[SPOSC] Listener error: {e}")

            await asyncio.sleep(retry_interval)

    async def _start_listener(self, listen_ip="127.0.0.1", listen_port=9000):
        if self._listener_enabled:
            self.log("[SPOSC] Listener already active. Skipping.")
            return

        try:
            self.log(f"[SPOSC] Starting OSC listener on {listen_ip}:{listen_port}")
            self._osc_server = AsyncIOOSCUDPServer(
                (listen_ip, listen_port),
                self._dispatcher,
                asyncio.get_event_loop()
            )
            self._transport, _ = await self._osc_server.create_serve_endpoint()
            self._listener_enabled = True
            self.log("[SPOSC] Listener is now running.")
        except Exception as e:
            self.log(f"[SPOSC] Failed to bind OSC listener: {e}")
            self._listener_enabled = False

    def registerOscListener(self, path, val_type, callback_fn):
        def handler(address, *args):
            self.log(f"[OSC Listener] Received → {address} {args}")
            callback_fn(args)

        self._dispatcher.map(path, handler)
        self.log(f"[DEBUG] Dispatcher mapping keys: {list(self._dispatcher._map.keys())}")
        self.log(f"[OSC Listener] Registered → {path} with type {val_type}")

    def safe_push_output(self, plugin):
        def _push():
            plugin.pushStatusOutput()

        threading.Timer(0.01, _push).start()

    def safe_push_input(self, plugin):
        def _push():
            plugin.pushStatusInput()

        threading.Timer(0.01, _push).start()

    def send(self, address, val_type, raw_val, plugin, val_list=None):
        try:
            val_type_str = val_type.value if isinstance(val_type, Enum) else val_type if val_type else None

            values = []  # List to hold final values

            if val_type_str == "M":  # Mixed type, process multiple types
                for val in raw_val:
                    # Process each value based on its actual type
                    if isinstance(val, int):
                        values.append(int(val))
                    elif isinstance(val, float):
                        values.append(float(val))
                    elif isinstance(val, bool):
                        values.append(bool(val))
                    elif isinstance(val, str):
                        values.append(str(val))
                    elif isinstance(val, list):
                        values.append(str(val))  # Handle lists (if needed)
                    else:
                        values.append(str(val))  # Default to string if unsure
            else:

                if isinstance(raw_val, list):

                    for val in raw_val:
                        if val_type_str == "i":
                            values.append(int(val))
                        elif val_type_str == "f":
                            values.append(float(val))
                        elif val_type_str == "B":
                            if val == "True":
                                values.append(True)
                            else:
                                values.append(False)
                        elif val_type_str == "s":
                            values.append(str(val))
                        elif val_type_str == "h":
                            values.append(int(val))
                        elif val_type_str == "d":
                            values.append(float(val))
                        elif val_type_str == "c":
                            values.append(str(val)[0] if str(val) else '\0')
                        elif val_type_str == "b":
                            values.append(val if isinstance(val, bytes) else str(val).encode('utf-8'))
                        elif val_type_str == "r":
                            values.append(self.rgb_floats_to_rgba_int(val[0], val[1], val[2], val[3]))
                        elif val_type_str == "m":
                            values.append(int(val) if val else 0)
                        elif val_type_str == "t":
                            values.append(int(val) if val else 0)
                        elif val_type_str == "N":
                            values.append(None)
                        elif val_type_str == "I":
                            values.append(float('inf'))
                        else:
                            values.append(str(val))
                else:
                    if val_type_str == "i":
                        values.append(int(raw_val))
                    elif val_type_str == "f":
                        values.append(float(raw_val))
                    elif val_type_str == "B":
                        if raw_val == "True":
                            values.append(True)
                        else:
                            values.append(False)
                    elif val_type_str == "s":
                        values.append(str(raw_val))
                    elif val_type_str == "h":
                        values.append(int(raw_val))
                    elif val_type_str == "d":
                        values.append(float(raw_val))
                    elif val_type_str == "c":
                        values.append(str(raw_val)[0] if str(raw_val) else '\0')
                    elif val_type_str == "b":
                        values.append(raw_val if isinstance(raw_val, bytes) else str(raw_val).encode('utf-8'))
                    elif val_type_str == "r":
                        values.append(self.rgb_floats_to_rgba_int(raw_val[0], raw_val[1], raw_val[2], raw_val[3]))
                    elif val_type_str == "m":
                        values.append(int(raw_val) if raw_val else 0)
                    elif val_type_str == "t":
                        values.append(int(raw_val) if raw_val else 0)
                    elif val_type_str == "N":
                        values.append(None)
                    elif val_type_str == "I":
                        values.append(float('inf'))
                    else:
                        values.append(str(raw_val))

            full_address = self.prefix + address
            self.log(f"{self.host}:{self.port}")
            self.log(f"{self.prefix}")
            self.log(f"{address}")

            # Building the OSC message with multiple arguments (send values as array of arguments)
            builder = OscMessageBuilder(address=full_address)

            for value in values:  # Add each value as a separate argument to the OSC message
                if val_type_str is not None and value is not None:
                    builder.add_arg(value)  # Add each value as a separate argument
                    self.log(f"[SEND] With arg → {full_address} {value} ({val_type_str})")
                else:
                    self.log(f"[SEND] Sending bare OSC message: {full_address}")

            msg = builder.build()

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(msg.dgram, (self.host, self.port))
            self.safe_push_output(plugin)
            sock.close()

            self.log(f"[SEND] To {self.host}:{self.port} → {full_address} {values if values else '[no args]'}")

        except Exception as e:
            self.log(f"[Send OSC] Error: {e}")

    def update_config(self, host, port, prefix=""):
        self.host = host
        self.port = port
        self.prefix = prefix
        self.log(f"[Init] OSC config updated → {host}:{port} | prefix='{prefix}'")

    def add_action_param_int(self, action, name, min_val, max_val, default, suffix=None):
        param = action.addIntParameter(name, int(default), int(min_val), int(max_val))

    def add_action_param_float(self, action, name, min_val, max_val, default, suffix=None):
        param = action.addFloatParameter(name, float(default), float(min_val), float(max_val))

    def add_action_param_string(self, action, name, default, suffix=None):
        param = action.addStringParameter(name, str(default))

    def add_action_param_IP(self, action, name, default, suffix=None):
        action.addIPParameter(name, bool(default))

    def add_action_param_Array(self, action, name, default, options, suffix=None):
        action.addEnumParameter(name, int(default), str(options))

    def add_action_param_Color(self, action, name, suffix=None):
        action.addColorParameter(name)

    def add_action_param_Bool(self, action, name, default, suffix=None):
        action.addBoolParameter(name, bool(default))

    def oscAction(self, plugin, name, group, desc, val_type, path, *values):
        # Extract dynamic path definitions
        path_defs = list(re.finditer(r'\{([^{}]+)\}', path))
        value_defs = []

        if values:
            # Unpack all dynamic value definitions
            for v in values:
                value_defs += list(re.finditer(r'\{([^{}]+)\}', v))

        expected_total = 1 + len(path_defs) + len(value_defs)

        def action_callback(*args):
            if len(args) < expected_total:
                plugin.logError(f"[oscAction] Not enough args: got {len(args)}, expected {expected_total}")
                return

            callback = args[0]
            dyn_args = args[1:expected_total]

            # --- PATH substitution ---
            tempPath = path
            for i, match in enumerate(path_defs):
                ddef = match.group(1)
                parts = [p.strip() for p in ddef.split(",")]
                param_type = parts[0]
                raw_val = dyn_args[i]

                try:
                    # Handle integer and float types
                    if param_type in ["I", "F"]:
                        val = float(raw_val)
                        modifier = parts[6] if len(parts) > 6 else None
                        if modifier:
                            if modifier.startswith("*"):
                                val *= float(modifier[1:])
                            elif modifier.startswith("/"):
                                val /= float(modifier[1:])
                            elif modifier.startswith("+"):
                                val += float(modifier[1:])
                            elif modifier.startswith("-"):
                                val -= float(modifier[1:])
                        replacement = str(int(val)) if param_type == "I" else str(val)

                    # Handle boolean type
                    elif param_type == "B":
                        replacement = str(bool(raw_val and str(raw_val).lower() not in ["false", "0", "no"]))

                    # Handle array type
                    elif param_type == "A":
                        options = parts[3].split(";")
                        replacement = options[int(raw_val)].strip()

                    # Handle string type (no conversion needed, just pass raw value)
                    elif param_type == "S":
                        replacement = str(raw_val)  # Leave as string

                    else:
                        replacement = str(raw_val)

                except Exception as e:
                    plugin.logError(f"[oscAction] Substitution error in path ({ddef}): {e}")
                    replacement = str(raw_val)

                tempPath = tempPath.replace("{" + ddef + "}", replacement)

            plugin.log(f"[oscAction] Final OSC path → {tempPath}")

            # --- VALUE substitution ---
            send_values = []
            if val_type != OSCTypes.Bare and values and value_defs:
                for i, match in enumerate(value_defs):
                    ddef = match.group(1)
                    parts = [p.strip() for p in ddef.split(",")]
                    param_type = parts[0]
                    raw_val = dyn_args[len(path_defs) + i]

                    try:
                        # Handle integer and float types
                        if param_type in ["I", "F"]:
                            val = float(raw_val)
                            modifier = parts[6] if len(parts) > 6 else None
                            if modifier:
                                if modifier.startswith("*"):
                                    val *= float(modifier[1:])
                                elif modifier.startswith("/"):
                                    val /= float(modifier[1:])
                                elif modifier.startswith("+"):
                                    val += float(modifier[1:])
                                elif modifier.startswith("-"):
                                    val -= float(modifier[1:])
                            replacement = int(val) if param_type == "I" else val

                        # Handle boolean type
                        elif param_type == "B":
                            replacement = str(bool(raw_val and str(raw_val).lower() not in ["false", "0", "no"]))

                        # Handle array type
                        elif param_type == "A":
                            options = parts[3].split(";")
                            replacement = options[int(raw_val)].strip()

                        # Handle string type (no conversion needed, just pass raw value)
                        elif param_type == "S":
                            replacement = str(raw_val)  # Leave as string

                        else:
                            replacement = str(raw_val)

                    except Exception as e:
                        plugin.logError(f"[oscAction] Substitution error in value ({ddef}): {e}")
                        replacement = str(raw_val)

                    send_values.append(replacement)

                plugin.log(f"[oscAction] Final send_values → {send_values}")

            # Now pass the list of values to _send_osc_action (ensure it's passed as a list)
            self._send_osc_action(callback, val_type=val_type, address=tempPath, plugin=plugin, value=send_values)

        # Register action
        action = plugin.addAction(name, group, action_callback)

        # Register UI parameters from full defs (path + values)
        all_defs = [m.group(1) for m in path_defs + value_defs]
        for ddef in all_defs:
            parts = [p.strip() for p in ddef.split(",")]
            param_type = parts[0]
            param_name = parts[1]
            suffix = None

            try:
                if param_type in ["I", "F"]:
                    default = parts[2]
                    min_val = parts[3]
                    max_val = parts[4]
                    suffix = parts[5] if len(parts) > 5 else None
                    if param_type == "I":
                        self.add_action_param_int(action, param_name, min_val, max_val, default, suffix)
                    else:
                        self.add_action_param_float(action, param_name, min_val, max_val, default, suffix)

                elif param_type == "A":
                    default = parts[2]
                    options = parts[3]
                    suffix = parts[4] if len(parts) > 4 else None
                    self.add_action_param_Array(action, param_name, default, options, suffix)

                elif param_type == "S":
                    default = parts[2]
                    suffix = parts[3] if len(parts) > 3 else None
                    self.add_action_param_string(action, param_name, default, suffix)

                elif param_type == "B":
                    default = parts[2]
                    suffix = parts[3] if len(parts) > 3 else None
                    self.add_action_param_Bool(action, param_name, default, suffix)

                elif param_type == "IP":
                    default = parts[2]
                    suffix = parts[3] if len(parts) > 3 else None
                    self.add_action_param_IP(action, param_name, default, suffix)

                elif param_type == "C":
                    self.add_action_param_Color(action, param_name)

            except Exception as e:
                plugin.logError(f"[oscAction] Failed to register param ({ddef}): {e}")

    def oscCustomAction(self, plugin, name, group, desc):
        value_type_options = ["Int", "Float", "String", "Bool"]

        def action_callback(callback, path, val_type_index, value):
            try:
                val_type = value_type_options[val_type_index]

                if val_type == "Int":
                    coerced_value = int(value)
                elif val_type == "Float":
                    coerced_value = float(value)
                elif val_type in ["Bool", "True", "False"]:
                    coerced_value = str(value).lower() in ["true", "True", "1", "yes", "on"]
                elif val_type == "String":
                    coerced_value = str(value)
                else:
                    coerced_value = value

                plugin.log(f"[oscCustomAction] Sending: {path} ({val_type}) = {coerced_value}")
                self._send_osc_action(
                    callback,
                    val_type=val_type,
                    address=path,
                    plugin=plugin,
                    value=coerced_value
                )

            except Exception as e:
                plugin.logError(f"[oscCustomAction] Failed to send: {e}")
                callback(False)

        action = plugin.addAction(name, group, action_callback)
        action.addStringParameter("Path", "/custom/path")
        action.addEnumParameter("Value Type", 1, ";".join(value_type_options))
        action.addStringParameter("Value", "0.5")

    def rgb_floats_to_rgba_int(self, r, g, b, a=1.0):
        r = int(max(0, min(255, r * 255)))
        g = int(max(0, min(255, g * 255)))
        b = int(max(0, min(255, b * 255)))
        a = int(max(0, min(255, a * 255)))

        rgba = (r << 24) | (g << 16) | (b << 8) | a
        print(f"RGBA Packed Int: {hex(rgba)} ({rgba})")
        return rgba


    def extract_dynamic_def(self, text):
        return re.findall(r'\{([^{}]+)\}', text)

    def _send_osc_action(self, callback, *, val_type=None, address=None, plugin=None, value=None, val_list=None):
        try:
            plugin.log(f"[send_osc_action] Final OSC Path: {address} | Value: {value}")
            self.send(address, val_type, value, plugin, val_list)
            callback(True)
        except Exception as e:
            plugin.logError(f"[send_osc_action] Error: {e}")
            callback(False)

    def register_dynamic_event(self, plugin, dyn_def):
        for ddef in dyn_def:
            parts = [p.strip() for p in ddef.split(",")]
            if parts[0] == "E":
                event_name = parts[1]
                script_event = parts[2]
                tokens = [t.strip() for t in parts[3:]] if len(parts) > 3 else []
                plugin.registerEvent(event_name, script_event, scriptTokens=tokens)
                plugin.log(f"[event] Registered event: {event_name} → {script_event} (tokens: {tokens})")

    def oscEvent(self, plugin, name, group, desc, val_type, path, callback_fn):
        dyn_def = self.extract_dynamic_def(path)

        def listener_callback(*args):
            plugin.log(f"[oscEvent] Received → {path} args={args}")
            self.safe_push_input(plugin)
            callback_fn(args)

        self.registerOscListener(
            path,
            val_type.value if isinstance(val_type, Enum) else val_type,
            listener_callback
        )

        self.register_dynamic_event(plugin, dyn_def)

        plugin.log(f"[oscEvent] Registered OSC listener on {path} with type {val_type}")

    def oscEntityReceiver(self, plugin, name, val_type, path, entity_path):
        def handler(args):
            value = args[0] if args else None
            plugin.log(f"[oscEntityReceiver] {path} received: {value}")
            self.safe_push_input(plugin)
            plugin.entities.getSubPath(entity_path, True).value = value

        self.registerOscListener(
            path,
            val_type.value if isinstance(val_type, Enum) else val_type,
            handler
        )

        plugin.log(f"[oscEntityReceiver] Listening on {path}, updates → entity '{entity_path}'")

    def restart(self, listen_ip="127.0.0.1", listen_port=9000, retry_interval=5):
        def delayed_restart():
            self.disable()
            time.sleep(1.0)  # wait for port to be freed
            self.enable(listen_ip=listen_ip, listen_port=listen_port, retry_interval=retry_interval)

        threading.Thread(target=delayed_restart, daemon=True).start()
