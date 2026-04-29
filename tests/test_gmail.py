from __future__ import annotations

from unittest.mock import MagicMock, call

from gcli.gmail import GmailClient


def _make_stub(msg_id: str) -> dict:
    return {"id": msg_id, "threadId": f"t{msg_id}"}


def _make_full_message(msg_id: str, sender: str = "alice@example.com") -> dict:
    return {
        "id": msg_id,
        "snippet": f"snippet-{msg_id}",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": "bob@example.com"},
                {"name": "Subject", "value": f"Subject {msg_id}"},
                {"name": "Date", "value": "Mon, 01 Jan 2026 10:00:00 +0000"},
            ],
            "body": {"data": ""},
        },
    }


def _make_service(list_side_effect: list, get_side_effect: list | None = None) -> MagicMock:
    """Build a minimal fake Gmail service."""
    service = MagicMock()
    list_mock = service.users.return_value.messages.return_value.list.return_value
    list_mock.execute.side_effect = list_side_effect

    get_mock = service.users.return_value.messages.return_value.get.return_value
    if get_side_effect is not None:
        get_mock.execute.side_effect = get_side_effect
    return service


# ---------------------------------------------------------------------------
# match_all=True – multiple pages
# ---------------------------------------------------------------------------


def test_search_messages_match_all_fetches_all_pages() -> None:
    """With match_all=True, pagination follows nextPageToken until exhausted."""
    page1_stubs = [_make_stub(str(i)) for i in range(1, 4)]
    page2_stubs = [_make_stub(str(i)) for i in range(4, 7)]
    all_stubs = page1_stubs + page2_stubs
    full_messages = [_make_full_message(s["id"]) for s in all_stubs]

    service = _make_service(
        list_side_effect=[
            {"messages": page1_stubs, "nextPageToken": "tok2"},
            {"messages": page2_stubs},
        ],
        get_side_effect=full_messages,
    )

    client = GmailClient(service)
    result = client.search_messages(query="invoice", match_all=True)

    assert len(result.messages) == 6
    assert [r["id"] for r in result.messages] == [str(i) for i in range(1, 7)]
    assert result.pages == 2

    # Verify list was called twice with correct page tokens
    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    assert len(list_calls) == 2
    assert list_calls[0] == call(userId="me", q="invoice", pageToken=None, maxResults=500)
    assert list_calls[1] == call(userId="me", q="invoice", pageToken="tok2", maxResults=500)


def test_search_messages_match_all_three_pages() -> None:
    """match_all=True correctly chains through three pages."""
    ids_p1 = [str(i) for i in range(1, 4)]
    ids_p2 = [str(i) for i in range(4, 7)]
    ids_p3 = [str(i) for i in range(7, 10)]
    all_ids = ids_p1 + ids_p2 + ids_p3

    service = _make_service(
        list_side_effect=[
            {"messages": [_make_stub(i) for i in ids_p1], "nextPageToken": "t2"},
            {"messages": [_make_stub(i) for i in ids_p2], "nextPageToken": "t3"},
            {"messages": [_make_stub(i) for i in ids_p3]},
        ],
        get_side_effect=[_make_full_message(i) for i in all_ids],
    )

    client = GmailClient(service)
    result = client.search_messages(query="invoice", match_all=True)

    assert len(result.messages) == 9
    assert result.pages == 3
    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    assert len(list_calls) == 3


# ---------------------------------------------------------------------------
# match_all=True – single page / empty
# ---------------------------------------------------------------------------


def test_search_messages_match_all_single_page() -> None:
    """match_all=True with no nextPageToken returns all messages from one page."""
    stubs = [_make_stub(str(i)) for i in range(1, 4)]
    service = _make_service(
        list_side_effect=[{"messages": stubs}],
        get_side_effect=[_make_full_message(s["id"]) for s in stubs],
    )

    client = GmailClient(service)
    result = client.search_messages(query="invoice", match_all=True)

    assert len(result.messages) == 3
    assert result.pages == 1
    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    assert len(list_calls) == 1


def test_search_messages_match_all_empty_results() -> None:
    """match_all=True with zero matching messages returns an empty list."""
    service = _make_service(list_side_effect=[{"messages": []}])
    client = GmailClient(service)
    result = client.search_messages(query="invoice", match_all=True)

    assert result.messages == []
    assert result.pages == 1
    service.users.return_value.messages.return_value.list.assert_called_once()
    service.users.return_value.messages.return_value.get.assert_not_called()


def test_search_messages_match_all_response_without_messages_key() -> None:
    """match_all=True handles a response with no 'messages' key (e.g., 0 results)."""
    service = _make_service(list_side_effect=[{}])
    client = GmailClient(service)
    result = client.search_messages(query="invoice", match_all=True)

    assert result.messages == []
    assert result.pages == 1


# ---------------------------------------------------------------------------
# match_all=False – respects max_results
# ---------------------------------------------------------------------------


def test_search_messages_limited_by_max_results_single_page() -> None:
    """Without match_all, only max_results messages are returned."""
    stubs = [_make_stub(str(i)) for i in range(1, 11)]
    service = _make_service(
        list_side_effect=[{"messages": stubs, "nextPageToken": "more"}],
        get_side_effect=[_make_full_message(s["id"]) for s in stubs],
    )

    client = GmailClient(service)
    result = client.search_messages(query="invoice", max_results=5)

    assert len(result.messages) == 5
    assert result.pages == 1
    # Only one list call because max_results was satisfied within the first page
    assert service.users.return_value.messages.return_value.list.call_count == 1


def test_search_messages_limited_by_max_results_across_pages() -> None:
    """Without match_all, stops fetching pages as soon as max_results is reached."""
    page1_stubs = [_make_stub(str(i)) for i in range(1, 4)]
    page2_stubs = [_make_stub(str(i)) for i in range(4, 7)]

    service = _make_service(
        list_side_effect=[
            {"messages": page1_stubs, "nextPageToken": "tok2"},
            {"messages": page2_stubs},
        ],
        get_side_effect=[_make_full_message(str(i)) for i in range(1, 7)],
    )

    client = GmailClient(service)
    result = client.search_messages(query="invoice", max_results=5)

    assert len(result.messages) == 5
    assert result.pages == 2
    # Two list calls: first page gave 3 results, second gave the remaining 2 needed
    assert service.users.return_value.messages.return_value.list.call_count == 2


def test_search_messages_default_max_results_is_25() -> None:
    """Default max_results of 25 is used when neither argument is provided."""
    stubs = [_make_stub(str(i)) for i in range(1, 30)]
    service = _make_service(
        list_side_effect=[{"messages": stubs[:25]}],
        get_side_effect=[_make_full_message(s["id"]) for s in stubs[:25]],
    )

    client = GmailClient(service)
    result = client.search_messages(query="invoice")

    assert len(result.messages) == 25
    first_call = service.users.return_value.messages.return_value.list.call_args_list[0]
    assert first_call.kwargs["maxResults"] == 25


# ---------------------------------------------------------------------------
# match_all=True uses maxResults=500 per page
# ---------------------------------------------------------------------------


def test_search_messages_match_all_requests_500_per_page() -> None:
    """With match_all=True, each list call requests the maximum 500 per page."""
    stubs = [_make_stub(str(i)) for i in range(1, 4)]
    service = _make_service(
        list_side_effect=[{"messages": stubs}],
        get_side_effect=[_make_full_message(s["id"]) for s in stubs],
    )

    client = GmailClient(service)
    client.search_messages(query="invoice", match_all=True)

    first_call = service.users.return_value.messages.return_value.list.call_args_list[0]
    assert first_call.kwargs["maxResults"] == 500
