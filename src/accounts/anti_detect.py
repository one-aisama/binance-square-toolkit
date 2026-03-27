"""Cross-account anti-detection rules."""


def are_own_accounts(
    account_id_1: str, account_id_2: str, all_account_ids: set[str]
) -> bool:
    """Check if two accounts both belong to us. Never interact between own accounts."""
    return account_id_1 in all_account_ids and account_id_2 in all_account_ids


def should_skip_post_by_author(
    post_author_id: str, own_account_ids: set[str]
) -> bool:
    """Skip posts authored by any of our own accounts."""
    return post_author_id in own_account_ids
