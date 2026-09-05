import unittest

from tests.paths import ROOT


class AFileHasOneReasonToChange(unittest.TestCase):
    def test_one_file_one_responsibility(self) -> None:
        exceptions = {
            "scripts/minervini/risk.py": "예상 진입·보유 모드가 동일한 최종 판정·상태 규약을 공유하는 단일 리듀서다.",
        }
        self.assertTrue(all(reason.strip() for reason in exceptions.values()), "크기 예외에는 책임이 하나인 이유가 필요하다")
        oversized = []
        for directory, pattern, limit in ((ROOT / "scripts/minervini", "*.py", 1000), (ROOT / "tests", "test_*.py", 500)):
            for path in directory.rglob(pattern):
                relative = path.relative_to(ROOT).as_posix()
                lines = len(path.read_text(encoding="utf-8").splitlines())
                if lines > limit and relative not in exceptions:
                    oversized.append(f"{relative}: {lines}/{limit}줄")
        self.assertEqual(oversized, [], "책임이 둘 이상이면 쪼개고, 하나면 예외 목록에 이유를 적어라: " + "; ".join(oversized))
