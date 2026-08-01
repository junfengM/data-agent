from app.tools.preflight import (
    SEMANTIC_LAYER_MAX_BYTES,
    load_semantic_layer,
    load_source_category_config,
)


def test_load_semantic_layer_rejects_non_yaml_file(tmp_path):
    path = tmp_path / "semantic.json"
    path.write_text('{"metrics": [{"name": "revenue"}]}', encoding="utf-8")

    layer = load_semantic_layer(path)

    assert layer.metrics == []
    assert layer.dimensions == []


def test_load_semantic_layer_rejects_symlink(tmp_path):
    target = tmp_path / "semantic.yaml"
    target.write_text("metrics:\n  - name: revenue\n", encoding="utf-8")
    link = tmp_path / "linked.yaml"
    link.symlink_to(target)

    layer = load_semantic_layer(link)

    assert layer.metrics == []


def test_load_semantic_layer_rejects_oversized_file(tmp_path):
    path = tmp_path / "semantic.yaml"
    path.write_text("#" * (SEMANTIC_LAYER_MAX_BYTES + 1), encoding="utf-8")

    layer = load_semantic_layer(path)

    assert layer.metrics == []
    assert layer.dimensions == []


def test_load_source_category_config_rejects_non_yaml_file(tmp_path):
    path = tmp_path / "source-categories.json"
    path.write_text('{"categories": [{"id": "sales"}]}', encoding="utf-8")

    categories = load_source_category_config(path)

    assert categories == []


def test_load_source_category_config_accepts_yaml_file(tmp_path):
    path = tmp_path / "source-categories.yaml"
    path.write_text(
        "categories:\n"
        "  - id: sales\n"
        "    label: Sales\n"
        "    placeholder: ~~sales\n",
        encoding="utf-8",
    )

    categories = load_source_category_config(path)

    assert len(categories) == 1
    assert categories[0].id == "sales"
