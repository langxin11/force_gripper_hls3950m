import unittest

from hls3950_gripper.client import GripperClient
from hls3950_gripper.transport import SimulatedTransport


class GripperClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GripperClient(SimulatedTransport())

    def test_position_command_updates_both_fingers(self) -> None:
        self.client.enable()
        status = self.client.command_position(0.25, 0.75)
        self.assertEqual(status.left_position, 1024)
        self.assertEqual(status.right_position, 3071)

    def test_position_range_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            self.client.command_position(-0.1, 0.5)

    def test_disabled_controller_rejects_position(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "controller_disabled"):
            self.client.command_position(0.5, 0.5)


if __name__ == "__main__":
    unittest.main()
