"""Check SCORE admission guards without opening hardware or loading a module."""
from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'tools/crown-score'
spec = importlib.util.spec_from_loader('crown_score', SourceFileLoader('crown_score', str(path)))
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


class ScoreGuards(unittest.TestCase):
    def test_unconfigured_power_translation_or_clock_rejects_admission(self):
        good = {0x1406402c: 0x10000f, 0x14064034: 0x10000f,
                0x16c20000: 4, 0x16c30000: 4, 0x1a24104c: 2, 0x1a241844: 11}
        score.check_registers(good.__getitem__)
        for address, value in ((0x1406402c, 0), (0x14064034, 0),
                               (0x16c20000, 5), (0x16c30000, 5),
                               (0x1a24104c, 1), (0x1a241844, 0)):
            with self.subTest(address=hex(address)), self.assertRaises(RuntimeError):
                score.check_registers(({**good, address: value}).__getitem__)

    def test_exit_success_alone_does_not_validate_dsp_arithmetic(self):
        self.assertTrue(score.correct_result('A.B       0 / 256 wrong (0.000%)\n', False))
        self.assertFalse(score.correct_result('A.B       1 / 256 wrong (0.390%)\n', False))
        self.assertFalse(score.correct_result('request: ioctl 0 (ok), ret 0\n', False))
        self.assertTrue(score.correct_result('wrong: sum>>16 256, floor-each 0, '
                                            'round-each 256, floor-each-32 0 (of 256)', True))
        self.assertFalse(score.correct_result('floor-each 0, floor-each-32 1 (of 256)', True))

    def test_config_order_and_comments_do_not_change_identity(self):
        original = 'CONFIG_A=y\n# CONFIG_C is not set\nCONFIG_B=m\n'
        reordered = '# timestamp\nCONFIG_B=m\nCONFIG_A=y\n'
        self.assertEqual(score.config_hash(original), score.config_hash(reordered))
        self.assertNotEqual(score.config_hash(original), score.config_hash('CONFIG_A=y\nCONFIG_B=y\n'))


if __name__ == '__main__':
    unittest.main()
