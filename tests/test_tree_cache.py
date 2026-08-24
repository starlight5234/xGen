"""
Unit tests for TreeCacheStore and WindowTreeCache.
"""

import pytest
from lxml import etree
from xgen.core.tree_cache import TreeCacheStore, WindowTreeCache
from xgen.core.tree_parser import TreeParser, UINode


@pytest.fixture(autouse=True)
def clean_cache():
    store = TreeCacheStore.instance()
    store.clear_all()
    yield
    store.clear_all()


def test_store_and_retrieve_cache():
    store = TreeCacheStore.instance()
    sample_xml = "<AppiumAUT><Window Name='App1'><Button Name='OK'/></Window></AppiumAUT>"
    root = TreeParser.parse(sample_xml)
    lxml_tree = etree.fromstring(sample_xml.encode("utf-8"))

    cache = WindowTreeCache(
        window_handle="0x0001",
        raw_xml=sample_xml,
        parsed_root=root,
        lxml_tree=lxml_tree
    )

    store.set("0x0001", cache)
    assert store.get("0x0001") is not None
    assert store.get("0x0001").window_handle == "0x0001"
    assert store.get_active().window_handle == "0x0001"


def test_multi_window_cache_switching():
    store = TreeCacheStore.instance()

    xml1 = "<AppiumAUT><Window Name='Window 1'/></AppiumAUT>"
    xml2 = "<AppiumAUT><Window Name='Window 2'/></AppiumAUT>"

    cache1 = WindowTreeCache("0x0001", xml1, TreeParser.parse(xml1), etree.fromstring(xml1.encode()))
    cache2 = WindowTreeCache("0x0002", xml2, TreeParser.parse(xml2), etree.fromstring(xml2.encode()))

    store.set("0x0001", cache1)
    store.set("0x0002", cache2)

    assert set(store.all_handles()) == {"0x0001", "0x0002"}

    store.set_active_handle("0x0002")
    assert store.get_active().window_handle == "0x0002"
    assert store.get_active().parsed_root.children[0].name == "Window 2"


def test_merge_transient_into_cache():
    store = TreeCacheStore.instance()
    sample_xml = "<AppiumAUT><Window Name='App'><Pane Name='Body'/></Window></AppiumAUT>"
    root = TreeParser.parse(sample_xml)
    lxml_tree = etree.fromstring(sample_xml.encode())

    cache = WindowTreeCache("0x0001", sample_xml, root, lxml_tree)
    store.set("0x0001", cache)

    # Transient node
    menu = UINode(tag="Menu", attributes={"Name": "Popup"})
    store.merge_transient("0x0001", menu)

    updated_cache = store.get("0x0001")
    # Verify both parsed tree and lxml tree have the new node
    assert TreeParser.find_by_bounding_rect(updated_cache.parsed_root, None, "Menu") or any(c.tag == "Menu" for c in updated_cache.parsed_root.children)

    # Test XPath execution on updated live lxml tree
    matches = updated_cache.lxml_tree.xpath("//Menu[@Name='Popup']")
    assert len(matches) == 1
