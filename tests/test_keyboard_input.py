import ctypes
import unittest
from unittest.mock import patch

import keyboard_input
from keyboard_input import HARDWAREINPUT, INPUT, INPUT_UNION, KEYBDINPUT, MOUSEINPUT


class WindowsInputLayoutTests(unittest.TestCase):
    def test_sendinput_structures_match_windows_abi(self):
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(ctypes.sizeof(KEYBDINPUT), 24)
            self.assertEqual(ctypes.sizeof(MOUSEINPUT), 32)
            self.assertEqual(ctypes.sizeof(INPUT_UNION), 32)
            self.assertEqual(ctypes.sizeof(INPUT), 40)
        else:
            self.assertEqual(ctypes.sizeof(KEYBDINPUT), 16)
            self.assertEqual(ctypes.sizeof(MOUSEINPUT), 24)
            self.assertEqual(ctypes.sizeof(INPUT), 28)
        self.assertLessEqual(ctypes.sizeof(HARDWAREINPUT), ctypes.sizeof(INPUT_UNION))

    @unittest.skipIf(keyboard_input.pydirectinput is None, "PyDirectInput is not installed")
    def test_game_backend_uses_pydirectinput_without_pause(self):
        with patch.object(keyboard_input.pydirectinput, "keyDown", return_value=True) as down:
            keyboard_input.send_key("A", True)
            down.assert_called_once_with("a", _pause=False)
        with patch.object(keyboard_input.pydirectinput, "keyUp", return_value=True) as up:
            keyboard_input.send_key("1", False)
            up.assert_called_once_with("1", _pause=False)

    @unittest.skipIf(keyboard_input.pydirectinput is None, "PyDirectInput is not installed")
    def test_jis_symbol_keys_use_physical_scan_code_aliases(self):
        expected = {"^": "=", "@": "[", "[": "]"}
        for labelled_key, direct_key in expected.items():
            with self.subTest(labelled_key=labelled_key):
                with patch.object(keyboard_input.pydirectinput, "keyDown", return_value=True) as down:
                    keyboard_input.send_key(labelled_key, True)
                    down.assert_called_once_with(direct_key, _pause=False)


if __name__ == "__main__":
    unittest.main()
