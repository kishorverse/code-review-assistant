"""Find documents that share tags with a search query."""


def matching_documents(
    documents: dict[str, list[str]], wanted: list[str]
) -> list[str]:
    """Ids of the documents that have at least one ``wanted`` tag."""
    matches = []
    for doc_id, tags in documents.items():
        for tag in tags:
            if tag in wanted:
                matches.append(doc_id)
                break
    return matches


def unique_tags(documents: dict[str, list[str]]) -> list[str]:
    """Every tag used by any document, in first-seen order."""
    seen: list[str] = []
    for tags in documents.values():
        for tag in tags:
            if tag not in seen:
                seen.append(tag)
    return seen
