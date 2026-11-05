import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('startup_log', Path(__file__).resolve().parents[1] / 'ops/check-startup-log.py')
log = importlib.util.module_from_spec(spec)
spec.loader.exec_module(log)
HEADER = '[19:21:46] [Server thread/WARN]: [net.minecraft.world.entity.EntityType] Serialization errors:'
DETAIL = ": Failed to decode value '[{id:\"forge:entity_gravity\"}]' from field 'attributes': Unknown registry key in ResourceKey[minecraft:root / minecraft:attribute]: forge:entity_gravity; Unknown registry key in ResourceKey[minecraft:root / minecraft:attribute]: forge:step_height_addition"


class StartupLogTest(unittest.TestCase):
    def test_recognizes_only_the_known_warning_envelope_and_attributes(self):
        self.assertEqual(([], 1), log.inspect(HEADER + '\n' + DETAIL))
        self.assertTrue(log.inspect(HEADER.replace('/WARN', '/ERROR') + '\n' + DETAIL)[0])
        self.assertTrue(log.inspect(HEADER + '\n' + DETAIL.replace('forge:entity_gravity', 'minecraft:missing_attribute'))[0])
        self.assertTrue(log.inspect(HEADER + '\n' + DETAIL + '; Unknown registry key in another registry')[0])
        self.assertTrue(log.inspect(DETAIL)[0])

    def test_other_startup_failures_remain_fatal_next_to_the_known_warning(self):
        for problem in ('Failed to load datapack', 'Unknown registry minecraft:blocks', 'Missing required feature', 'watchdog', 'IllegalStateException', '[Server thread/ERROR]: plugin failed'):
            failures, count = log.inspect(HEADER + '\n' + DETAIL + '\n' + problem)
            self.assertEqual(1, count)
            self.assertEqual([(3, problem)], failures)


if __name__ == '__main__':
    unittest.main()
