"""Built-in prompt templates.

Templates are plain strings with ``{{variable}}`` placeholders. They are seeded
into the ``prompt_templates`` table on first start, and the authoring UI can
override any of them without touching code — the database always wins.

Keeping the prompts here (rather than only in the database) means a fresh
install is immediately usable and a corrupt database cannot leave the writer
without a single prompt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """One versioned prompt template."""

    key: str
    name: str
    operation: str
    system: str
    user: str
    variables: tuple[str, ...]
    description: str = ""


_WRITER = (
    "你是一位资深的中文长篇小说写作者，擅长把大纲落成有画面感、有情绪、有推进力的正文。"
    "写作时严格遵守：人物性格与前文设定一致；不重复已经写过的情节；"
    "用具体动作与对白推进故事，而不是概述；不输出标题、解释、注释或 Markdown 标记。"
)

_OUTLINER = (
    "你是一位资深的长篇小说策划。你擅长把故事拆成可执行的章节大纲，"
    "每一章都有明确目标、冲突和结尾钩子。输出简洁、可执行，不要写正文。"
)

_OUTLINE_SCHEMER = (
    "你是一位资深的长篇小说策划。你擅长把故事拆成可执行的章节大纲，"
    "每一章都有明确目标、冲突和结尾钩子。"
    "输出必须是严格的 JSON 对象本身，不要 Markdown 代码块，不要任何解释文字。"
)

_REVIEWER = (
    "你是一位严谨的长篇小说责编，负责检查连贯性。"
    "只依据给出的事实判断，指出问题并给出原文证据；没有问题就明确写「未发现」。"
    "不要改写正文，只输出检查结论。"
)

EDITOR = (
    "你是一位中文编辑。改写、扩写、润色时保持原意、人称、时态与人物性格不变，"
    "只输出改写后的文本本身，不要解释，不要加引号，不要保留 Markdown 标记。"
)

_SUMMARIZER = (
    "你是一位长篇小说记忆整理员。你的任务是把一章正文压缩成可复用的记忆卡片："
    "只陈述正文里确凿发生的事实，不推测、不评论、不润色、不续写。"
    "输出必须是严格的 JSON 对象本身，不要 Markdown 代码块，不要任何解释文字。"
)

#: Bumped whenever a built-in template changes materially. ``PromptService``
#: stores the version it last seeded in ``app_meta`` and, on an upgrade, appends
#: a **new** ``prompt_templates`` version for rows that are still pristine —
#: never silently keeps rendering the old text, and never overwrites an
#: author-edited row (see ``LEGACY_USER_TEXTS`` below).
BUILTIN_VERSION = 2

#: The section v2 added to the three templates that steer a chapter. It is its
#: own constant because the seeder rebuilds the **v1** text of those templates by
#: removing it: a stored row equal to that reconstruction is pristine, so a new
#: version may be appended; anything else is an author edit and stays as is.
#: Future versions can extend this into a per-version mapping.
FORESHADOW_SECTION = (
    "【伏笔与后续规划（尚未发生，只作方向约束，严禁写成已发生）】\n"
    "{{foreshadows}}\n\n"
)

#: Prompt used by the L1 memory layer (``chapter_summaries``). It is deliberately
#: **not** part of :data:`OPERATIONS`: summarising is bookkeeping, not something
#: the author triggers from the writing toolbar, and it must never run on the
#: autosave path (that would burn tokens on every keystroke pause).
SUMMARY_PROMPT_KEY = "memory.summary"

#: Prompt used when an outline is **persisted** into the ``outlines`` table
#: (``AIService.generate_outline``). Like :data:`SUMMARY_PROMPT_KEY` it is
#: deliberately **not** part of :data:`OPERATIONS`: the toolbar's ``outline``
#: operation still returns free text for the editor, while this one is a
#: structured write.
OUTLINE_PROMPT_KEY = "outline.structured"

PROMPTS: tuple[PromptSpec, ...] = (
    PromptSpec(
        key="outline.chapter",
        name="章节大纲生成",
        operation="outline",
        description="根据主线与前文，为下一章生成可执行的章节大纲。",
        system=_OUTLINER,
        user=(
            "小说类型：{{novel_type}}\n"
            "故事简介：{{synopsis}}\n\n"
            "【前文概要】\n{{context}}\n\n"
            + FORESHADOW_SECTION
            + "请为下一章设计章节大纲，严格按以下结构输出：\n"
            "- 章节标题\n"
            "- 章节目标\n"
            "- 核心冲突\n"
            "- 参与人物\n"
            "- 关键事件（3-5 条）\n"
            "- 情节转折\n"
            "- 埋下的伏笔\n"
            "- 章节结尾状态\n"
            "- 预计字数\n\n"
            "写作要求：{{instruction}}"
        ),
        variables=("novel_type", "synopsis", "context", "foreshadows", "instruction"),
    ),
    PromptSpec(
        key=OUTLINE_PROMPT_KEY,
        name="章节大纲（结构化落库）",
        operation="outline.structured",
        description="生成可落库的结构化章节大纲（写入 outlines 表）。",
        system=_OUTLINE_SCHEMER,
        user=(
            "小说类型：{{novel_type}}\n"
            "故事简介：{{synopsis}}\n\n"
            "【前情提要】\n{{context}}\n\n"
            "【已有大纲 / 上一级大纲】\n{{outline}}\n\n"
            "请输出严格 JSON 对象，字段与类型固定如下：\n"
            '{"title": "章节标题", "goal": "本章目标", "conflict": "核心冲突", '
            '"characters": ["出场人物"], "key_events": ["关键事件"], '
            '"twists": "情节转折", "foreshadows": ["埋下的伏笔"], '
            '"ending": "章节结尾状态", "target_word_count": 2000}\n'
            "要求：title 简洁可读；goal / conflict / twists / ending 各写一句话；"
            "characters / key_events / foreshadows 是短词数组，没有内容就留空数组；"
            "target_word_count 是整数。\n"
            "写作要求：{{instruction}}\n"
            "只输出 JSON 本身，不要代码块标记，不要解释。"
        ),
        variables=("novel_type", "synopsis", "context", "outline", "instruction"),
    ),
    PromptSpec(
        key="write.chapter",
        name="章节正文生成",
        operation="write",
        description="按章节大纲与历史记忆生成本章正文。",
        system=_WRITER,
        user=(
            "【本章大纲】\n{{outline}}\n\n"
            "【必须衔接的前文】\n{{context}}\n\n"
            + FORESHADOW_SECTION
            + "【本章要求】\n{{instruction}}\n\n"
            "【目标字数】约 {{target_words}} 字\n\n"
            "请直接输出本章正文。"
        ),
        variables=("outline", "context", "foreshadows", "instruction", "target_words"),
    ),
    PromptSpec(
        key="write.continue",
        name="续写",
        operation="continue",
        description="从光标位置或正文结尾自然接续。",
        system=_WRITER,
        user=(
            "【已有正文（结尾处续写）】\n{{context}}\n\n"
            + FORESHADOW_SECTION
            + "【续写要求】\n{{instruction}}\n\n"
            "请从已有正文的结尾自然接续，不要重复已有内容，不要输出标题或解释。"
        ),
        variables=("context", "foreshadows", "instruction"),
    ),
    PromptSpec(
        key="edit.expand",
        name="扩写",
        operation="expand",
        description="在不改变原意的前提下扩充细节。",
        system=EDITOR,
        user=(
            "【需要扩写的段落】\n{{selection}}\n\n"
            "【扩写要求】\n{{instruction}}\n\n"
            "请只输出扩写后的文本。"
        ),
        variables=("selection", "instruction", "context"),
    ),
    PromptSpec(
        key="edit.rewrite",
        name="改写",
        operation="rewrite",
        description="按指定要求重新组织内容。",
        system=EDITOR,
        user=(
            "【需要改写的段落】\n{{selection}}\n\n"
            "【改写要求】\n{{instruction}}\n\n"
            "请只输出改写后的文本。"
        ),
        variables=("selection", "instruction", "context"),
    ),
    PromptSpec(
        key="edit.polish",
        name="润色",
        operation="polish",
        description="提升语言质量，不改变情节。",
        system=EDITOR,
        user=(
            "【需要润色的段落】\n{{selection}}\n\n"
            "【润色要求】\n{{instruction}}\n\n"
            "请只输出润色后的文本。"
        ),
        variables=("selection", "instruction", "context"),
    ),
    PromptSpec(
        key="review.consistency",
        name="连贯性检查",
        operation="review",
        description="检查人物性格、时间线、地点与已知信息是否冲突。",
        system=_REVIEWER,
        user=(
            "【本章正文】\n{{context}}\n\n"
            "【人物与设定】\n{{characters}}\n\n"
            "【已知事件与时间线】\n{{events}}\n\n"
            "请逐项检查并给出结论，格式为「问题 / 证据 / 建议」：\n"
            "1. 人物性格是否与设定冲突\n"
            "2. 时间线是否矛盾\n"
            "3. 地点是否一致\n"
            "4. 是否重复已发生的事件\n"
            "5. 是否出现人物不应知道的信息\n\n"
            "某项没有问题就写「未发现」。"
        ),
        variables=("context", "characters", "events", "instruction"),
    ),
    PromptSpec(
        key=SUMMARY_PROMPT_KEY,
        name="章节摘要（L1 记忆）",
        operation="summary",
        description="把一章正文压缩成结构化摘要，供后续章节的「前情提要」复用。",
        system=_SUMMARIZER,
        user=(
            "【章节标题】{{chapter_title}}\n\n"
            "【章节正文】\n{{context}}\n\n"
            "请输出严格 JSON 对象，字段与类型固定如下：\n"
            '{"summary": "120-200 字的事件摘要", '
            '"characters": ["出场人物"], '
            '"events": ["本章关键事件"], '
            '"locations": ["地点"], '
            '"keywords": ["便于检索的关键词"], '
            '"foreshadows": ["埋下或回收的伏笔"], '
            '"plot_progress": "一句话概括主线推进"}\n'
            "要求：summary 按时间顺序用陈述句概括本章发生了什么，120-200 字；"
            "characters / events / locations / keywords / foreshadows 都是短词数组，"
            "没有内容就留空数组；plot_progress 只写一句。\n"
            "只输出 JSON 本身，不要代码块标记，不要解释。"
        ),
        variables=("chapter_title", "context"),
    ),
)

PROMPTS_BY_KEY: dict[str, PromptSpec] = {spec.key: spec for spec in PROMPTS}

#: User text shipped by the **previous** built-in version for every template the
#: current version changed, reconstructed by dropping :data:`FORESHADOW_SECTION`.
#: ``PromptService.ensure_builtins`` compares a stored row against these to tell
#: a pristine row (safe to append a new version for) from an author edit (which
#: must never be overwritten).
LEGACY_USER_TEXTS: dict[str, tuple[str, ...]] = {
    spec.key: (spec.user.replace(FORESHADOW_SECTION, ""),)
    for spec in PROMPTS
    if FORESHADOW_SECTION in spec.user
}

#: Operations the AI API exposes, mapped to the prompt key they use.
OPERATIONS: dict[str, str] = {
    "outline": "outline.chapter",
    "write": "write.chapter",
    "continue": "write.continue",
    "expand": "edit.expand",
    "rewrite": "edit.rewrite",
    "polish": "edit.polish",
    "review": "review.consistency",
}
