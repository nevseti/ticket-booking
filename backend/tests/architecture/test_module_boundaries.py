"""Автоматическая проверка границ модульного монолита (см. docs/adr/0001).

1. Из чужого модуля можно импортировать только `facade` и `events`.
2. Фасады вызываются только по разрешённому направлению зависимостей.
3. Ядро (`app.core`, `app.shared`) не зависит от модулей.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
MODULES_PKG = "app.modules"

# Чьи фасады модуль имеет право вызывать. События (`events`) можно импортировать
# откуда угодно: подписка на событие не создаёт синхронной зависимости.
ALLOWED_FACADE_DEPS: dict[str, set[str]] = {
    "identity": set(),
    "catalog": {"identity"},
    "booking": {"identity", "catalog"},
    "orders": {"identity", "catalog", "booking"},
    "notifications": {"identity"},
}
PUBLIC_SUBMODULES = {"facade", "events"}


@dataclass(frozen=True)
class ImportRef:
    file: Path
    line: int
    target: str  # полное имя импортируемого модуля/объекта


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP_DIR.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(current: str, is_package: bool, level: int, module: str | None) -> str:
    base = current.split(".")
    if not is_package:
        base = base[:-1]
    if level > 1:
        base = base[: -(level - 1)]
    return ".".join([*base, module] if module else base)


def _imports(path: Path) -> list[ImportRef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current = _module_name(path)
    is_package = path.name == "__init__.py"
    refs: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            refs += [ImportRef(path, node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative(current, is_package, node.level, node.module)
                if node.level
                else node.module or ""
            )
            # `from app.modules.booking import facade` → app.modules.booking.facade
            refs += [ImportRef(path, node.lineno, f"{base}.{alias.name}") for alias in node.names]
    return refs


def _owner(dotted: str) -> tuple[str | None, str | None]:
    """app.modules.booking.facade.X → ('booking', 'facade')."""
    parts = dotted.split(".")
    if parts[:2] != ["app", "modules"] or len(parts) < 3:
        return None, None
    return parts[2], parts[3] if len(parts) > 3 else None


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_all_modules_are_described() -> None:
    on_disk = {p.name for p in (APP_DIR / "modules").iterdir() if (p / "__init__.py").exists()}
    assert on_disk == set(ALLOWED_FACADE_DEPS)


def test_modules_use_only_public_interfaces_of_each_other() -> None:
    violations: list[str] = []
    for module in ALLOWED_FACADE_DEPS:
        for file in _python_files(APP_DIR / "modules" / module):
            for ref in _imports(file):
                owner, sub = _owner(ref.target)
                if owner is None or owner == module:
                    continue
                where = f"{ref.file.relative_to(APP_DIR.parent)}:{ref.line} → {ref.target}"
                if sub not in PUBLIC_SUBMODULES:
                    violations.append(f"импорт внутренностей чужого модуля: {where}")
                elif sub == "facade" and owner not in ALLOWED_FACADE_DEPS[module]:
                    violations.append(f"запрещённое направление зависимости: {where}")
    if violations:
        pytest.fail("\n".join(violations), pytrace=False)


def test_core_does_not_depend_on_modules() -> None:
    violations = [
        f"{ref.file.relative_to(APP_DIR.parent)}:{ref.line} → {ref.target}"
        for layer in ("core", "shared")
        for file in _python_files(APP_DIR / layer)
        for ref in _imports(file)
        if ref.target.startswith(MODULES_PKG)
    ]
    if violations:
        pytest.fail("\n".join(violations), pytrace=False)
