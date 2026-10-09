"""The person's comments on the gaps of an evidence map (EF-SYN-03, tranche 3.5)."""

from pydantic import AwareDatetime, BaseModel, ConfigDict

__all__ = ["GapComment", "latest_comments"]


class GapComment(BaseModel):
    """A comment on one cell of the map of two fields (table ``gap_comment``). A new
    comment on the same cell replaces the previous one, which stays recorded; an empty
    comment withdraws it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    rows_field: str
    columns_field: str
    row: str
    column: str
    text: str
    created_at: AwareDatetime
    reviewer_id: str


def latest_comments(
    comments: list[GapComment], rows_field: str, columns_field: str
) -> dict[tuple[str, str], str]:
    """The comment in force on each cell of the map of ``rows_field`` by
    ``columns_field``."""
    found: dict[tuple[str, str], str] = {}
    for comment in sorted(comments, key=lambda c: (c.created_at, c.id)):
        if (comment.rows_field, comment.columns_field) != (rows_field, columns_field):
            continue
        if comment.text:
            found[comment.row, comment.column] = comment.text
        else:
            found.pop((comment.row, comment.column), None)
    return found
