"""Reading the search strategy form of the « Recherche » page (EF-REC-01).

Each block has the fields ``bloc-<code>-libelle``, ``-pcc``, ``-role``, ``-termes`` (one
term per line) and ``-retirer``; the empty block at the end of the form uses the code
``nouveau``. The form is turned back into rows when it holds errors, so that what was
typed is shown again.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from revue_portee.domain.criteria import PccElement
from revue_portee.domain.search import (
    BLOCK_CODE,
    LANGUAGES,
    BlockRole,
    ConceptBlock,
    Limits,
    SearchStrategy,
    Term,
    TermSyntaxError,
    format_term,
    next_block_code,
    parse_term,
)
from revue_portee.i18n import gettext as _

__all__ = ["NEW_BLOCK", "BlockRow", "StrategyForm", "read_strategy_form", "rows_of"]

NEW_BLOCK = "nouveau"


@dataclass(frozen=True, slots=True)
class BlockRow:
    code: str
    label: str = ""
    pcc: str = ""
    role: str = BlockRole.INCLUDE.value
    terms: str = ""  # one term per line


@dataclass(frozen=True, slots=True)
class StrategyForm:
    rows: tuple[BlockRow, ...]
    year_from: str = ""
    year_to: str = ""
    languages: tuple[str, ...] = ()
    rationale: str = ""
    errors: tuple[str, ...] = ()
    strategy: SearchStrategy | None = None  # None when errors were found


def rows_of(strategy: SearchStrategy | None) -> tuple[BlockRow, ...]:
    if strategy is None:
        return ()
    return tuple(
        BlockRow(
            code=b.code,
            label=b.label,
            pcc="" if b.pcc_element is None else b.pcc_element.value,
            role=b.role.value,
            terms="\n".join(format_term(t) for t in b.terms),
        )
        for b in strategy.blocks
    )


def _year(value: str, errors: list[str]) -> int | None:
    value = value.strip()
    if not value:
        return None
    if not value.isdigit() or not 1800 <= int(value) <= 2100:
        errors.append(_("Years are written with four digits, from 1800 to 2100."))
        return None
    return int(value)


def read_strategy_form(
    form: Mapping[str, str], languages: Sequence[str], *, used_codes: Iterable[str] = ()
) -> StrategyForm:
    """The strategy described by the form, or the errors that prevent reading it.

    ``used_codes`` are the block codes of every earlier version: a new block never gets
    the code of a removed one."""
    codes = []
    for key in form:
        if key.startswith("bloc-") and key.endswith("-termes"):
            code = key.removeprefix("bloc-").removesuffix("-termes")
            if BLOCK_CODE.match(code) or code == NEW_BLOCK:
                codes.append(code)
    known = [c for c in codes if c != NEW_BLOCK] + list(used_codes)
    rows: list[BlockRow] = []
    blocks: list[ConceptBlock] = []
    errors: list[str] = []
    for code in codes:
        prefix = f"bloc-{code}-"
        row = BlockRow(
            code=code,
            label=form.get(prefix + "libelle", "").strip(),
            pcc=form.get(prefix + "pcc", ""),
            role=form.get(prefix + "role", BlockRole.INCLUDE.value),
            terms=form.get(prefix + "termes", ""),
        )
        lines = [line.strip() for line in row.terms.splitlines() if line.strip()]
        if form.get(prefix + "retirer") or (code == NEW_BLOCK and not lines and not row.label):
            continue
        rows.append(row)
        terms: list[Term] = []
        name = row.label or (_("new block") if code == NEW_BLOCK else code)
        for line in lines:
            try:
                term = parse_term(line)
            except TermSyntaxError as error:
                errors.append(
                    _("Block « {block} », line « {line} »: {problem}").format(
                        block=name, line=line, problem=_syntax_message(str(error))
                    )
                )
                continue
            if term not in terms:
                terms.append(term)
        if not row.label:
            errors.append(_("Block « {block} »: the label is required.").format(block=name))
            continue
        try:
            pcc = PccElement(row.pcc) if row.pcc else None
            role = BlockRole(row.role)
        except ValueError:
            errors.append(_("Block « {block} »: invalid choice.").format(block=name))
            continue
        final_code = (
            next_block_code(known + [b.code for b in blocks]) if code == NEW_BLOCK else code
        )
        blocks.append(
            ConceptBlock(
                code=final_code, label=row.label, pcc_element=pcc, role=role, terms=tuple(terms)
            )
        )
    year_from = _year(form.get("annee_debut", ""), errors)
    year_to = _year(form.get("annee_fin", ""), errors)
    chosen = tuple(code for code in languages if code in LANGUAGES)
    if year_from and year_to and year_from > year_to:
        errors.append(_("The first year comes after the last year."))
    result = StrategyForm(
        rows=tuple(rows),
        year_from=form.get("annee_debut", "").strip(),
        year_to=form.get("annee_fin", "").strip(),
        languages=chosen,
        rationale=form.get("justification", "").strip(),
        errors=tuple(dict.fromkeys(errors)),
    )
    if errors:
        return result
    limits = Limits(year_from=year_from, year_to=year_to, languages=chosen)
    return replace(result, strategy=SearchStrategy(blocks=tuple(blocks), limits=limits))


def _syntax_message(problem: str) -> str:
    messages = {
        "empty term": _("empty term"),
        "a prefix needs a term": _("a prefix needs a term"),
        "unbalanced parentheses or quotes": _("unbalanced parentheses or quotes"),
        "invalid descriptor": _("invalid descriptor"),
        "quotes, parentheses and brackets are not allowed in a term": _(
            "quotes, parentheses and brackets are not allowed in a term"
        ),
        "one term per line: use separate lines instead of AND, OR, NOT": _(
            "one term per line: use separate lines instead of AND, OR, NOT"
        ),
    }
    return messages.get(problem, problem)
