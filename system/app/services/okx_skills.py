from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OKXSkillDescriptor:
    name: str
    path: Path
    description: str


class OKXSkillRegistry:
    def __init__(self, *, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "okx-onchainos-skills"

    def list_skills(self) -> list[OKXSkillDescriptor]:
        skills: list[OKXSkillDescriptor] = []
        if not self.root.exists():
            return skills

        for skill_dir in sorted(self.root.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            skills.append(
                OKXSkillDescriptor(
                    name=skill_dir.name,
                    path=skill_file,
                    description=self._extract_description(skill_file.read_text(encoding="utf-8")),
                )
            )
        return skills

    def load_skill(self, skill_name: str) -> str:
        skill_file = self.root / skill_name / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Unknown OKX skill: {skill_name}")
        return skill_file.read_text(encoding="utf-8")

    def load_reference(self, skill_name: str, relative_path: str) -> str:
        base = self.root / skill_name
        target = (base / relative_path).resolve()
        if not str(target).startswith(str(base.resolve())):
            raise ValueError("Reference path escapes the skill directory.")
        if not target.exists():
            raise FileNotFoundError(f"Reference not found: {skill_name}/{relative_path}")
        return target.read_text(encoding="utf-8")

    def _extract_description(self, content: str) -> str:
        for line in content.splitlines():
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip().strip('"')
        return ""
