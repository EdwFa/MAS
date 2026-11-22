"""Скиллы в мини-harness P-0042 (лекция 14, слайды 10 и 17).

Уровень 1 — catalog(): строка на скилл, добавляется к правилам.
Уровень 2 — read_skill: обычный инструмент реестра, политика «разрешить».
Уровень 3 — run_script: скрипт скилла в песочнице случая.

Стартовый код. Что дописывают студенты — в README практикума.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "P-0042"))          # каркас P-0042 рядом в репозитории

from p0042.tools import Toolbox, tool                          # noqa: E402


# --- уровни 1 и 2: слайд 10 -------------------------------------------------

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")     # без дефиса в начале, в конце и двух подряд
RESERVED = ("anthropic", "claude")                    # запрещены в name на платформе Claude
XML_RE = re.compile(r"<[^>]+>")


def validate(meta, folder):
    """Проверки спецификации agentskills.io; список нарушений (пустой — скилл годен)."""
    errs = []
    name, desc = meta.get("name"), meta.get("description")
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not NAME_RE.match(name):
        errs.append("name: 1–64 символа, a-z, 0-9 и дефис, без дефиса по краям и двух подряд")
    elif name != folder:
        errs.append(f"name {name!r} не совпадает с папкой {folder!r}")
    elif any(w in name for w in RESERVED):
        errs.append("name: слова anthropic и claude зарезервированы")
    if not isinstance(desc, str) or not 1 <= len(desc) <= 1024:
        errs.append("description: 1–1024 символа")
    elif XML_RE.search(desc):
        errs.append("description: без XML-тегов")
    comp = meta.get("compatibility")
    if comp is not None and not (isinstance(comp, str) and 1 <= len(comp) <= 500):
        errs.append("compatibility: 1–500 символов")
    return errs


def scan(root=HERE / "skills"):
    skills = {}
    for p in sorted(pathlib.Path(root).glob("*/SKILL.md")):
        _, front, body = p.read_text(encoding="utf-8").split("---", 2)
        meta = yaml.safe_load(front) or {}
        errs = validate(meta, p.parent.name)
        if errs:                                      # не assert: assert выключается флагом -O
            raise ValueError(f"{p}: " + "; ".join(errs))
        skills[meta["name"]] = {"desc": " ".join(meta["description"].split()),
                                "dir": p.parent, "body": body.strip()}
    return skills


def catalog(skills):                                           # уровень 1: в системный промпт
    lines = "\n".join(f"- {n}: {s['desc']}" for n, s in skills.items())
    return ("Скиллы. Если запрос подходит под описание — сначала вызови read_skill с именем скилла "
            "и следуй его шагам. Если не подходит — не читай.\n" + lines)


def read_skill(skills, name):                                  # уровень 2: результат вызова
    s = skills.get(name)
    return s["body"] if s else f"нет скилла {name}"


# --- уровень 3: песочница ---------------------------------------------------

class Sandbox:
    """Папка случая: cases/<case_id>/work/. Скрипт видит только её."""

    def __init__(self, root, case_id):
        self.dir = pathlib.Path(root) / "cases" / case_id
        (self.dir / "work").mkdir(parents=True, exist_ok=True)
        self.label = f"cases/{case_id}/"

    def put(self, name, obj):
        (self.dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

    def inside(self, rel):
        p = (self.dir / rel).resolve()
        return p if p.is_relative_to(self.dir.resolve()) else None

    def clear(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def run_script(skills, sandbox, skill, script, file, timeout=10):
    s = skills.get(skill)
    if s is None:
        return {"isError": True, "text": f"нет скилла {skill}"}
    path = (s["dir"] / script).resolve()
    if not path.is_relative_to((s["dir"] / "scripts").resolve()) or not path.is_file():
        return {"isError": True, "text": "скрипт должен лежать в scripts/ этого скилла"}
    target = sandbox.inside(file)
    if target is None or not target.is_file():
        return {"isError": True, "text": f"файл {file} не найден в песочнице случая"}
    # -I: изолированный режим Python; cwd — папка случая; без переменных окружения; лимит времени
    try:
        p = subprocess.run([sys.executable, "-I", str(path), str(target)], cwd=sandbox.dir,
                           capture_output=True, text=True, timeout=timeout, env={})
    except subprocess.TimeoutExpired:
        return {"isError": True, "text": f"скрипт не уложился в {timeout} с"}
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = {"stdout": p.stdout[-2000:]}
    return {"exit_code": p.returncode, "result": out, "sandbox": sandbox.label,
            **({"stderr": p.stderr[-500:]} if p.stderr else {})}


# --- инструменты для диспетчера ---------------------------------------------

class SkillToolbox(Toolbox):
    """Toolbox P-0042 + read_skill и run_script. Порядок проверки тот же: имя → схема → лимит → политика."""

    def __init__(self, fhir, rag=None, chart=None, skills=None, sandbox=None):
        super().__init__(fhir, rag, chart)
        self.skills, self.sandbox = skills or {}, sandbox
        if self.skills:
            self.registry["read_skill"] = self.read_skill
            self.registry["run_script"] = self.run_script

    @tool("read_skill", "Загрузить инструкцию скилла по имени из списка.",
          {"type": "object", "required": ["name"], "additionalProperties": False,
           "properties": {"name": {"type": "string"}}}, limit=3)
    def read_skill(self, name):
        return {"skill": name, "body": read_skill(self.skills, name)}

    @tool("run_script", "Запустить скрипт скилла над файлом из песочницы случая. Возвращает JSON скрипта.",
          {"type": "object", "required": ["skill", "script", "file"], "additionalProperties": False,
           "properties": {"skill": {"type": "string"},
                          "script": {"type": "string", "pattern": "^scripts/[A-Za-z0-9_.-]+\\.py$"},
                          "file": {"type": "string", "pattern": "^work/[A-Za-z0-9_.-]+$"}}}, limit=3)
    def run_script(self, skill, script, file):
        if self.sandbox is None:
            raise RuntimeError("песочница случая не подключена")
        return run_script(self.skills, self.sandbox, skill, script, file)
