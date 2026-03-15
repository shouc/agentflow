from agentflow.defaults import (
    bundled_fuzz_campaign_presets,
    bundled_template_names,
    bundled_template_path,
    bundled_template_support_files,
    bundled_templates,
    default_smoke_pipeline_path,
    load_bundled_template_yaml,
    render_bundled_template,
)
from agentflow.loader import load_pipeline_from_path


def test_bundled_templates_expose_descriptions_and_example_files():
    templates = bundled_templates()

    assert tuple(template.name for template in templates) == bundled_template_names()

    by_name = {template.name: template for template in templates}
    assert by_name["pipeline"].example_name == "pipeline.yaml"
    assert by_name["pipeline"].description == "Generic Codex/Claude/Kimi starter DAG."
    assert by_name["codex-fanout-repo-sweep"].example_name == "codex-fanout-repo-sweep.yaml"
    assert "8 review shards" in by_name["codex-fanout-repo-sweep"].description
    assert by_name["codex-repo-sweep-batched"].example_name == "codex-repo-sweep-batched.yaml"
    assert "fanout.batches" in by_name["codex-repo-sweep-batched"].description
    assert "node_defaults" in by_name["codex-repo-sweep-batched"].description
    assert tuple(parameter.name for parameter in by_name["codex-repo-sweep-batched"].parameters) == (
        "shards",
        "batch_size",
        "concurrency",
        "focus",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-matrix"].example_name == "fuzz/codex-fuzz-matrix.yaml"
    assert "fanout.matrix" in by_name["codex-fuzz-matrix"].description
    assert by_name["codex-fuzz-matrix-derived"].example_name == "fuzz/codex-fuzz-matrix-derived.yaml"
    assert "fanout.derive" in by_name["codex-fuzz-matrix-derived"].description
    assert by_name["codex-fuzz-matrix-curated"].example_name == "fuzz/codex-fuzz-matrix-curated.yaml"
    assert "fanout.exclude" in by_name["codex-fuzz-matrix-curated"].description
    assert by_name["codex-fuzz-matrix-128"].example_name == "fuzz/codex-fuzz-matrix-128.yaml"
    assert "128-shard Codex fuzz matrix" in by_name["codex-fuzz-matrix-128"].description
    assert by_name["codex-fuzz-hierarchical-128"].example_name == "fuzz/codex-fuzz-hierarchical-128.yaml"
    assert "per-target reducers" in by_name["codex-fuzz-hierarchical-128"].description
    assert by_name["codex-fuzz-hierarchical-grouped"].example_name == "fuzz/codex-fuzz-hierarchical-grouped.yaml"
    assert "fanout.group_by" in by_name["codex-fuzz-hierarchical-grouped"].description
    assert by_name["codex-fuzz-hierarchical-grouped"].support_files == (
        "manifests/codex-fuzz-hierarchical-grouped.axes.yaml",
    )
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-hierarchical-grouped"].parameters) == (
        "preset",
        "bucket_count",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-hierarchical-manifest"].example_name == "fuzz/codex-fuzz-hierarchical-manifest.yaml"
    assert "reducer families" in by_name["codex-fuzz-hierarchical-manifest"].description
    assert by_name["codex-fuzz-hierarchical-manifest"].support_files == (
        "manifests/codex-fuzz-hierarchical.axes.yaml",
        "manifests/codex-fuzz-hierarchical.families.yaml",
    )
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-hierarchical-manifest"].parameters) == (
        "preset",
        "bucket_count",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-matrix-manifest"].example_name == "fuzz/codex-fuzz-matrix-manifest.yaml"
    assert "fanout.matrix_path" in by_name["codex-fuzz-matrix-manifest"].description
    assert by_name["codex-fuzz-matrix-manifest"].support_files == ("manifests/codex-fuzz-matrix.axes.yaml",)
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-matrix-manifest"].parameters) == (
        "preset",
        "bucket_count",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-matrix-manifest-128"].example_name == "fuzz/codex-fuzz-matrix-manifest-128.yaml"
    assert "fanout.matrix_path" in by_name["codex-fuzz-matrix-manifest-128"].description
    assert by_name["codex-fuzz-matrix-manifest-128"].support_files == (
        "manifests/codex-fuzz-matrix-manifest-128.axes.yaml",
    )
    assert by_name["codex-fuzz-browser-128"].example_name == "fuzz/codex-fuzz-browser-128.yaml"
    assert "browser-surface" in by_name["codex-fuzz-browser-128"].description
    assert by_name["codex-fuzz-browser-128"].support_files == ("manifests/codex-fuzz-browser-128.axes.yaml",)
    assert by_name["codex-fuzz-preset-batched"].example_name == "fuzz/codex-fuzz-preset-batched.yaml"
    assert "fanout.preset" in by_name["codex-fuzz-preset-batched"].description
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-preset-batched"].parameters) == (
        "preset",
        "bucket_count",
        "batch_size",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-catalog"].example_name == "fuzz/codex-fuzz-catalog.yaml"
    assert "CSV shard catalog" in by_name["codex-fuzz-catalog"].description
    assert by_name["codex-fuzz-catalog"].support_files == ("manifests/codex-fuzz-catalog.csv",)
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-catalog"].parameters) == (
        "preset",
        "shards",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-catalog-batched"].example_name == "fuzz/codex-fuzz-catalog-batched.yaml"
    assert "fanout.batches" in by_name["codex-fuzz-catalog-batched"].description
    assert by_name["codex-fuzz-catalog-batched"].support_files == ("manifests/codex-fuzz-catalog.csv",)
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-catalog-batched"].parameters) == (
        "preset",
        "shards",
        "batch_size",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-catalog-grouped"].example_name == "fuzz/codex-fuzz-catalog-grouped.yaml"
    assert "fanout.group_by" in by_name["codex-fuzz-catalog-grouped"].description
    assert by_name["codex-fuzz-catalog-grouped"].support_files == ("manifests/codex-fuzz-catalog-grouped.csv",)
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-catalog-grouped"].parameters) == (
        "preset",
        "shards",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-batched"].example_name == "fuzz/codex-fuzz-batched.yaml"
    assert "fanout.batches" in by_name["codex-fuzz-batched"].description
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-batched"].parameters) == (
        "shards",
        "batch_size",
        "concurrency",
        "name",
        "working_dir",
    )
    assert by_name["codex-fuzz-swarm"].example_name == "fuzz/fuzz_codex_32.yaml"
    assert "defaults to 32 shards" in by_name["codex-fuzz-swarm"].description
    assert tuple(parameter.name for parameter in by_name["codex-fuzz-swarm"].parameters) == (
        "shards",
        "concurrency",
        "name",
        "working_dir",
    )


def test_bundled_fuzz_campaign_presets_expose_named_rosters():
    presets = bundled_fuzz_campaign_presets()

    assert tuple(preset.name for preset in presets) == ("oss-fuzz-core", "browser-surface", "protocol-stack")
    by_name = {preset.name: preset for preset in presets}
    assert by_name["oss-fuzz-core"].families[0] == {"target": "libpng", "corpus": "png"}
    assert by_name["browser-surface"].families == (
        {"target": "blink", "corpus": "html"},
        {"target": "v8", "corpus": "js"},
        {"target": "woff2", "corpus": "fonts"},
        {"target": "libwebp", "corpus": "webp"},
    )
    assert by_name["protocol-stack"].families[-1] == {"target": "openssl", "corpus": "tls"}


def test_bundled_smoke_pipeline_runs_both_agents_in_shared_kimi_bootstrap():
    pipeline = load_pipeline_from_path(default_smoke_pipeline_path())
    codex_node = next(node for node in pipeline.nodes if node.id == "codex_plan")
    claude_node = next(node for node in pipeline.nodes if node.id == "claude_review")

    assert pipeline.concurrency == 2
    assert codex_node.target.kind == "local"
    assert codex_node.target.bootstrap == "kimi"
    assert codex_node.target.shell == "bash"
    assert codex_node.target.shell_login is True
    assert codex_node.target.shell_interactive is True
    assert codex_node.target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert codex_node.depends_on == []
    assert claude_node.target.bootstrap == "kimi"
    assert claude_node.target.shell_init == ["command -v kimi >/dev/null 2>&1", "kimi"]
    assert claude_node.depends_on == []


def test_bundled_shell_init_smoke_template_is_available():
    assert "local-kimi-shell-init-smoke" in bundled_template_names()
    assert load_bundled_template_yaml("local-kimi-shell-init-smoke").startswith(
        "name: local-real-agents-kimi-shell-init-smoke\n"
    )


def test_bundled_shell_init_smoke_pipeline_runs_both_agents_in_explicit_shell_init_mode():
    pipeline = load_pipeline_from_path(str(bundled_template_path("local-kimi-shell-init-smoke")))
    codex_node = next(node for node in pipeline.nodes if node.id == "codex_plan")
    claude_node = next(node for node in pipeline.nodes if node.id == "claude_review")

    assert pipeline.concurrency == 2
    assert codex_node.target.kind == "local"
    assert codex_node.target.bootstrap is None
    assert codex_node.target.shell == "bash"
    assert codex_node.target.shell_login is True
    assert codex_node.target.shell_interactive is True
    assert codex_node.target.shell_init == "kimi"
    assert codex_node.depends_on == []
    assert claude_node.target.bootstrap is None
    assert claude_node.target.shell_init == "kimi"
    assert claude_node.depends_on == []


def test_bundled_shell_wrapper_smoke_template_is_available():
    assert "local-kimi-shell-wrapper-smoke" in bundled_template_names()
    assert load_bundled_template_yaml("local-kimi-shell-wrapper-smoke").startswith(
        "name: local-real-agents-kimi-shell-wrapper-smoke\n"
    )


def test_bundled_codex_fanout_repo_sweep_template_is_available():
    assert "codex-fanout-repo-sweep" in bundled_template_names()
    assert load_bundled_template_yaml("codex-fanout-repo-sweep").startswith(
        "name: codex-fanout-repo-sweep\n"
    )


def test_bundled_codex_repo_sweep_batched_template_is_available():
    assert "codex-repo-sweep-batched" in bundled_template_names()
    assert "\nname: codex-repo-sweep-batched-128\n" in f"\n{load_bundled_template_yaml('codex-repo-sweep-batched')}"


def test_bundled_codex_repo_sweep_batched_template_matches_default_example_file():
    expected = bundled_template_path("codex-repo-sweep-batched").read_text(encoding="utf-8")

    assert load_bundled_template_yaml("codex-repo-sweep-batched") == expected


def test_bundled_codex_repo_sweep_batched_template_accepts_overrides_and_scopes_batch_dependencies(tmp_path):
    rendered = load_bundled_template_yaml(
        "codex-repo-sweep-batched",
        values={
            "shards": "64",
            "batch_size": "8",
            "concurrency": "20",
            "focus": "security bugs, privilege boundaries, and missing coverage",
            "name": "custom-repo-sweep-64",
            "working_dir": "./custom_repo_sweep",
        },
    )

    assert "name: custom-repo-sweep-64\n" in rendered
    assert "working_dir: ./custom_repo_sweep\n" in rendered
    assert "concurrency: 20\n" in rendered
    assert "count: 64" in rendered
    assert "size: 8" in rendered
    assert "Focus on security bugs, privilege boundaries, and missing coverage." in rendered
    assert "node_defaults:" in rendered
    assert "agent_defaults:" in rendered
    assert "timeout_seconds: 900" in rendered
    assert "current.scope.ids" in rendered
    assert "current.scope.with_output.nodes" in rendered

    pipeline_path = tmp_path / "custom-repo-sweep.yaml"
    pipeline_path.write_text(rendered, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 20
    assert pipeline.fanouts["sweep"][:3] == ["sweep_00", "sweep_01", "sweep_02"]
    assert pipeline.fanouts["sweep"][-1] == "sweep_63"
    assert len(pipeline.fanouts["sweep"]) == 64
    assert pipeline.node_map["prepare"].agent == "codex"
    assert pipeline.node_map["prepare"].model == "gpt-5-codex"
    assert pipeline.node_map["prepare"].tools == "read_only"
    assert pipeline.node_map["sweep_00"].fanout_member["label"] == "slice 1/64"
    assert pipeline.node_map["sweep_00"].extra_args == ["--search", "-c", 'model_reasoning_effort="high"']
    assert pipeline.fanouts["batch_merge"] == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
        "batch_merge_6",
        "batch_merge_7",
    ]
    assert pipeline.node_map["batch_merge_0"].fanout_member["member_ids"] == [
        "sweep_00",
        "sweep_01",
        "sweep_02",
        "sweep_03",
        "sweep_04",
        "sweep_05",
        "sweep_06",
        "sweep_07",
    ]
    assert pipeline.node_map["batch_merge_7"].fanout_member["member_ids"] == [
        "sweep_56",
        "sweep_57",
        "sweep_58",
        "sweep_59",
        "sweep_60",
        "sweep_61",
        "sweep_62",
        "sweep_63",
    ]
    assert pipeline.node_map["merge"].depends_on == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
        "batch_merge_6",
        "batch_merge_7",
    ]


def test_bundled_codex_fuzz_matrix_template_is_available():
    assert "codex-fuzz-matrix" in bundled_template_names()
    assert "\nname: codex-fuzz-matrix\n" in f"\n{load_bundled_template_yaml('codex-fuzz-matrix')}"


def test_bundled_codex_fuzz_matrix_derived_template_is_available():
    assert "codex-fuzz-matrix-derived" in bundled_template_names()
    assert "\nname: codex-fuzz-matrix-derived\n" in f"\n{load_bundled_template_yaml('codex-fuzz-matrix-derived')}"


def test_bundled_codex_fuzz_matrix_curated_template_is_available():
    assert "codex-fuzz-matrix-curated" in bundled_template_names()
    assert "\nname: codex-fuzz-matrix-curated\n" in f"\n{load_bundled_template_yaml('codex-fuzz-matrix-curated')}"


def test_bundled_codex_fuzz_matrix_128_template_is_available():
    assert "codex-fuzz-matrix-128" in bundled_template_names()
    assert "\nname: codex-fuzz-matrix-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-matrix-128')}"


def test_bundled_codex_fuzz_hierarchical_128_template_is_available():
    assert "codex-fuzz-hierarchical-128" in bundled_template_names()
    assert "\nname: codex-fuzz-hierarchical-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-hierarchical-128')}"


def test_bundled_codex_fuzz_hierarchical_grouped_template_is_available():
    assert "codex-fuzz-hierarchical-grouped" in bundled_template_names()
    assert "\nname: codex-fuzz-hierarchical-grouped-64\n" in (
        f"\n{load_bundled_template_yaml('codex-fuzz-hierarchical-grouped')}"
    )
    assert bundled_template_support_files("codex-fuzz-hierarchical-grouped") == (
        "manifests/codex-fuzz-hierarchical-grouped.axes.yaml",
    )


def test_bundled_codex_fuzz_hierarchical_grouped_template_matches_default_example_files():
    expected_yaml = bundled_template_path("codex-fuzz-hierarchical-grouped").read_text(encoding="utf-8")
    expected_axes = (
        bundled_template_path("codex-fuzz-hierarchical-grouped").parent
        / "manifests"
        / "codex-fuzz-hierarchical-grouped.axes.yaml"
    ).read_text(encoding="utf-8")
    rendered = render_bundled_template("codex-fuzz-hierarchical-grouped")

    assert rendered.yaml == expected_yaml
    assert len(rendered.support_files) == 1
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-hierarchical-grouped.axes.yaml"
    assert rendered.support_files[0].content == expected_axes


def test_bundled_codex_fuzz_hierarchical_grouped_template_accepts_overrides_and_renders_support_file(tmp_path):
    rendered = render_bundled_template(
        "codex-fuzz-hierarchical-grouped",
        values={
            "bucket_count": "8",
            "concurrency": "32",
            "name": "custom-hierarchical-grouped-128",
            "working_dir": "./custom_hierarchical_grouped",
        },
    )

    assert "name: custom-hierarchical-grouped-128\n" in rendered.yaml
    assert "working_dir: ./custom_hierarchical_grouped\n" in rendered.yaml
    assert "concurrency: 32\n" in rendered.yaml
    assert "matrix_path: manifests/codex-fuzz-hierarchical-grouped.axes.yaml" in rendered.yaml
    assert "group_by:" in rendered.yaml
    assert "from: fuzzer" in rendered.yaml
    assert "{{ current.scope.ids | join(\", \") }}" in rendered.yaml
    assert "{{ shard.output }}" in rendered.yaml
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-hierarchical-grouped.axes.yaml"
    rendered_axes = rendered.support_files[0].content.strip().splitlines()
    assert rendered_axes[:4] == ["family:", "  - target: libpng", "    corpus: png", "  - target: libjpeg"]
    assert rendered_axes[-4:] == ["  - bucket: seed_007", "    seed: 4107", "  - bucket: seed_008", "    seed: 4108"]

    pipeline_path = tmp_path / "custom-hierarchical-grouped.yaml"
    pipeline_path.write_text(rendered.yaml, encoding="utf-8")
    support_path = tmp_path / rendered.support_files[0].relative_path
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(rendered.support_files[0].content, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng / asan / parser / seed_001"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith(
        "custom_hierarchical_grouped/agents/libpng_asan_seed_001_000"
    )
    assert pipeline.fanouts["family_merge"] == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]
    assert pipeline.node_map["family_merge_0"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["family_merge_0"].fanout_member["member_ids"][0] == "fuzzer_000"
    assert pipeline.node_map["family_merge_0"].fanout_member["member_ids"][-1] == "fuzzer_031"
    assert pipeline.node_map["family_merge_3"].fanout_member["target"] == "sqlite"
    assert pipeline.node_map["family_merge_0"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["family_merge_0"].depends_on[-1] == "fuzzer_031"
    assert pipeline.node_map["merge"].depends_on == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]


def test_bundled_codex_fuzz_hierarchical_manifest_template_is_available():
    assert "codex-fuzz-hierarchical-manifest" in bundled_template_names()
    assert "\nname: codex-fuzz-hierarchical-manifest-64\n" in f"\n{load_bundled_template_yaml('codex-fuzz-hierarchical-manifest')}"
    assert bundled_template_support_files("codex-fuzz-hierarchical-manifest") == (
        "manifests/codex-fuzz-hierarchical.axes.yaml",
        "manifests/codex-fuzz-hierarchical.families.yaml",
    )


def test_bundled_codex_fuzz_hierarchical_manifest_template_matches_default_example_files():
    template_dir = bundled_template_path("codex-fuzz-hierarchical-manifest").parent
    expected_yaml = bundled_template_path("codex-fuzz-hierarchical-manifest").read_text(encoding="utf-8")
    expected_axes = (template_dir / "manifests" / "codex-fuzz-hierarchical.axes.yaml").read_text(encoding="utf-8")
    expected_families = (template_dir / "manifests" / "codex-fuzz-hierarchical.families.yaml").read_text(
        encoding="utf-8"
    )
    rendered = render_bundled_template("codex-fuzz-hierarchical-manifest")

    assert rendered.yaml == expected_yaml
    assert len(rendered.support_files) == 2
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-hierarchical.axes.yaml"
    assert rendered.support_files[0].content == expected_axes
    assert rendered.support_files[1].relative_path == "manifests/codex-fuzz-hierarchical.families.yaml"
    assert rendered.support_files[1].content == expected_families


def test_bundled_codex_fuzz_hierarchical_manifest_template_accepts_overrides_and_renders_support_files(tmp_path):
    rendered = render_bundled_template(
        "codex-fuzz-hierarchical-manifest",
        values={
            "bucket_count": "8",
            "concurrency": "32",
            "name": "custom-hierarchical-manifest-128",
            "working_dir": "./custom_hierarchical_manifest",
        },
    )

    assert "name: custom-hierarchical-manifest-128\n" in rendered.yaml
    assert "working_dir: ./custom_hierarchical_manifest\n" in rendered.yaml
    assert "concurrency: 32\n" in rendered.yaml
    assert "matrix_path: manifests/codex-fuzz-hierarchical.axes.yaml" in rendered.yaml
    assert "values_path: manifests/codex-fuzz-hierarchical.families.yaml" in rendered.yaml
    assert len(rendered.support_files) == 2
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-hierarchical.axes.yaml"
    assert rendered.support_files[1].relative_path == "manifests/codex-fuzz-hierarchical.families.yaml"
    rendered_axes = rendered.support_files[0].content.strip().splitlines()
    assert rendered_axes[:4] == ["family:", "  - target: libpng", "    corpus: png", "  - target: libjpeg"]
    assert rendered_axes[-4:] == ["  - bucket: seed_007", "    seed: 4107", "  - bucket: seed_008", "    seed: 4108"]
    assert rendered.support_files[1].content.strip().splitlines() == [
        "- target: libpng",
        "  corpus: png",
        "- target: libjpeg",
        "  corpus: jpeg",
        "- target: freetype",
        "  corpus: fonts",
        "- target: sqlite",
        "  corpus: sql",
    ]

    pipeline_path = tmp_path / "custom-hierarchical.yaml"
    pipeline_path.write_text(rendered.yaml, encoding="utf-8")
    for support_file in rendered.support_files:
        support_path = tmp_path / support_file.relative_path
        support_path.parent.mkdir(parents=True, exist_ok=True)
        support_path.write_text(support_file.content, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng / asan / parser / seed_001"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith(
        "custom_hierarchical_manifest/agents/libpng_asan_seed_001_000"
    )
    assert pipeline.fanouts["family_merge"] == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]
    assert pipeline.node_map["family_merge_0"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["family_merge_3"].fanout_member["target"] == "sqlite"
    assert pipeline.node_map["merge"].depends_on == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]


def test_bundled_codex_fuzz_matrix_manifest_template_is_available():
    assert "codex-fuzz-matrix-manifest" in bundled_template_names()
    assert "\nname: codex-fuzz-matrix-manifest-64\n" in f"\n{load_bundled_template_yaml('codex-fuzz-matrix-manifest')}"
    assert bundled_template_support_files("codex-fuzz-matrix-manifest") == ("manifests/codex-fuzz-matrix.axes.yaml",)


def test_bundled_codex_fuzz_matrix_manifest_template_matches_default_example_files():
    expected_yaml = bundled_template_path("codex-fuzz-matrix-manifest").read_text(encoding="utf-8")
    expected_manifest = (
        bundled_template_path("codex-fuzz-matrix-manifest").parent / "manifests" / "codex-fuzz-matrix.axes.yaml"
    ).read_text(encoding="utf-8")
    rendered = render_bundled_template("codex-fuzz-matrix-manifest")

    assert rendered.yaml == expected_yaml
    assert len(rendered.support_files) == 1
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-matrix.axes.yaml"
    assert rendered.support_files[0].content == expected_manifest


def test_bundled_codex_fuzz_matrix_manifest_template_accepts_overrides_and_renders_support_file(tmp_path):
    rendered = render_bundled_template(
        "codex-fuzz-matrix-manifest",
        values={
            "bucket_count": "8",
            "concurrency": "32",
            "name": "custom-matrix-manifest-128",
            "working_dir": "./custom_matrix_manifest",
        },
    )

    assert "name: custom-matrix-manifest-128\n" in rendered.yaml
    assert "working_dir: ./custom_matrix_manifest\n" in rendered.yaml
    assert "concurrency: 32\n" in rendered.yaml
    assert "matrix_path: manifests/codex-fuzz-matrix.axes.yaml" in rendered.yaml
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-matrix.axes.yaml"
    rendered_axes = rendered.support_files[0].content.strip().splitlines()
    assert rendered_axes[:4] == ["family:", "  - target: libpng", "    corpus: png", "  - target: libjpeg"]
    assert rendered_axes[-4:] == ["  - bucket: seed_007", "    seed: 4107", "  - bucket: seed_008", "    seed: 4108"]

    pipeline_path = tmp_path / "custom-matrix-manifest.yaml"
    pipeline_path.write_text(rendered.yaml, encoding="utf-8")
    support_path = tmp_path / rendered.support_files[0].relative_path
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(rendered.support_files[0].content, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["fuzzer_127"].fanout_member["bucket"] == "seed_008"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith(
        "custom_matrix_manifest/agents/libpng_asan_seed_001_000"
    )
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_127"


def test_bundled_codex_fuzz_matrix_manifest_template_accepts_preset_overrides(tmp_path):
    rendered = render_bundled_template(
        "codex-fuzz-matrix-manifest",
        values={
            "preset": "browser-surface",
            "bucket_count": "8",
            "concurrency": "32",
            "name": "browser-fuzz-128",
            "working_dir": "./browser_fuzz",
        },
    )

    assert "description: Configurable 128-shard Codex fuzz matrix backed by a manifest sidecar generated from the `browser-surface` preset" in rendered.yaml
    assert rendered.support_files[0].content.strip().splitlines()[:4] == [
        "family:",
        "  - target: blink",
        "    corpus: html",
        "  - target: v8",
    ]
    assert "  - target: libwebp" in rendered.support_files[0].content

    pipeline_path = tmp_path / "browser-fuzz.yaml"
    pipeline_path.write_text(rendered.yaml, encoding="utf-8")
    support_path = tmp_path / rendered.support_files[0].relative_path
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(rendered.support_files[0].content, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.node_map["fuzzer_000"].fanout_member["target"] == "blink"
    assert pipeline.node_map["fuzzer_032"].fanout_member["target"] == "v8"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith("browser_fuzz/agents/blink_asan_seed_001_000")


def test_bundled_codex_fuzz_matrix_manifest_128_template_is_available():
    assert "codex-fuzz-matrix-manifest-128" in bundled_template_names()
    assert "\nname: codex-fuzz-matrix-manifest-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-matrix-manifest-128')}"
    assert bundled_template_support_files("codex-fuzz-matrix-manifest-128") == (
        "manifests/codex-fuzz-matrix-manifest-128.axes.yaml",
    )


def test_bundled_codex_fuzz_browser_128_template_is_available():
    assert "codex-fuzz-browser-128" in bundled_template_names()
    assert "\nname: codex-fuzz-browser-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-browser-128')}"
    assert bundled_template_support_files("codex-fuzz-browser-128") == ("manifests/codex-fuzz-browser-128.axes.yaml",)


def test_bundled_codex_fuzz_browser_128_template_matches_default_example_files():
    expected_yaml = bundled_template_path("codex-fuzz-browser-128").read_text(encoding="utf-8")
    expected_axes = (
        bundled_template_path("codex-fuzz-browser-128").parent / "manifests" / "codex-fuzz-browser-128.axes.yaml"
    ).read_text(encoding="utf-8")
    rendered = render_bundled_template("codex-fuzz-browser-128")

    assert rendered.yaml == expected_yaml
    assert len(rendered.support_files) == 1
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-browser-128.axes.yaml"
    assert rendered.support_files[0].content == expected_axes


def test_bundled_codex_fuzz_preset_batched_template_is_available():
    assert "codex-fuzz-preset-batched" in bundled_template_names()
    assert "\nname: codex-fuzz-preset-batched-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-preset-batched')}"


def test_bundled_codex_fuzz_preset_batched_template_matches_default_example_file():
    expected = bundled_template_path("codex-fuzz-preset-batched").read_text(encoding="utf-8")

    assert load_bundled_template_yaml("codex-fuzz-preset-batched") == expected


def test_bundled_codex_fuzz_preset_batched_template_accepts_overrides_and_expands_native_preset(tmp_path):
    rendered = load_bundled_template_yaml(
        "codex-fuzz-preset-batched",
        values={
            "preset": "protocol-stack",
            "bucket_count": "3",
            "batch_size": "6",
            "concurrency": "12",
            "name": "custom-preset-batched-48",
            "working_dir": "./custom_preset_batched",
        },
    )

    assert "name: custom-preset-batched-48\n" in rendered
    assert "working_dir: ./custom_preset_batched\n" in rendered
    assert "concurrency: 12\n" in rendered
    assert "name: protocol-stack" in rendered
    assert "bucket_count: 3" in rendered
    assert "size: 6" in rendered
    assert "Treat the built-in preset metadata as the source of truth" in rendered
    assert "{{ current.scope.ids | join(\", \") }}" in rendered

    pipeline_path = tmp_path / "custom-preset-batched.yaml"
    pipeline_path.write_text(rendered, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 12
    assert len(pipeline.fanouts["fuzzer"]) == 48
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_47"
    assert pipeline.node_map["fuzzer_00"].fanout_member["target"] == "c-ares"
    assert pipeline.node_map["fuzzer_12"].fanout_member["target"] == "nghttp2"
    assert pipeline.node_map["fuzzer_00"].fanout_member["label"] == "c-ares / asan / parser / seed_001"
    assert pipeline.node_map["fuzzer_47"].fanout_member["workspace"] == "agents/openssl_ubsan_seed_003_47"
    assert pipeline.node_map["fuzzer_00"].target.cwd.endswith("custom_preset_batched/agents/c-ares_asan_seed_001_00")
    assert pipeline.fanouts["batch_merge"] == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
        "batch_merge_6",
        "batch_merge_7",
    ]
    assert pipeline.node_map["batch_merge_0"].depends_on == [
        "fuzzer_00",
        "fuzzer_01",
        "fuzzer_02",
        "fuzzer_03",
        "fuzzer_04",
        "fuzzer_05",
    ]
    assert pipeline.node_map["merge"].depends_on == pipeline.fanouts["batch_merge"]


def test_bundled_codex_fuzz_catalog_template_is_available():
    assert "codex-fuzz-catalog" in bundled_template_names()
    assert "\nname: codex-fuzz-catalog-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-catalog')}"
    assert bundled_template_support_files("codex-fuzz-catalog") == ("manifests/codex-fuzz-catalog.csv",)


def test_bundled_codex_fuzz_catalog_template_matches_default_example_files():
    expected_yaml = bundled_template_path("codex-fuzz-catalog").read_text(encoding="utf-8")
    expected_catalog = (
        bundled_template_path("codex-fuzz-catalog").parent / "manifests" / "codex-fuzz-catalog.csv"
    ).read_text(encoding="utf-8")
    rendered = render_bundled_template("codex-fuzz-catalog")

    assert rendered.yaml == expected_yaml
    assert len(rendered.support_files) == 1
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-catalog.csv"
    assert rendered.support_files[0].content == expected_catalog


def test_bundled_codex_fuzz_catalog_template_accepts_overrides_and_renders_support_file(tmp_path):
    rendered = render_bundled_template(
        "codex-fuzz-catalog",
        values={
            "shards": "48",
            "concurrency": "12",
            "name": "custom-catalog-48",
            "working_dir": "./custom_catalog",
        },
    )

    assert "name: custom-catalog-48\n" in rendered.yaml
    assert "working_dir: ./custom_catalog\n" in rendered.yaml
    assert "concurrency: 12\n" in rendered.yaml
    assert "values_path: manifests/codex-fuzz-catalog.csv" in rendered.yaml
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-catalog.csv"
    rendered_rows = rendered.support_files[0].content.strip().splitlines()
    assert len(rendered_rows) == 49
    assert rendered_rows[0] == "label,target,corpus,sanitizer,focus,bucket,seed,workspace"
    assert rendered_rows[1].startswith("libpng/asan/parser/seed_001,libpng,png,asan,parser,seed_001,4101,agents/")
    assert rendered_rows[-1].startswith(
        "sqlite/ubsan/stateful/seed_003,sqlite,sql,ubsan,stateful,seed_003,4103,agents/"
    )

    pipeline_path = tmp_path / "custom-catalog.yaml"
    pipeline_path.write_text(rendered.yaml, encoding="utf-8")
    support_path = tmp_path / rendered.support_files[0].relative_path
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(rendered.support_files[0].content, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 12
    assert len(pipeline.fanouts["fuzzer"]) == 48
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_47"
    assert pipeline.node_map["fuzzer_00"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["fuzzer_16"].fanout_member["bucket"] == "seed_002"
    assert pipeline.node_map["fuzzer_47"].fanout_member["workspace"] == "agents/sqlite_ubsan_seed_003_47"
    assert pipeline.node_map["fuzzer_00"].target.cwd.endswith("custom_catalog/agents/libpng_asan_seed_001_00")
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_00"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_47"


def test_bundled_codex_fuzz_catalog_template_accepts_preset_overrides():
    rendered = render_bundled_template(
        "codex-fuzz-catalog",
        values={
            "preset": "protocol-stack",
            "shards": "48",
        },
    )

    rendered_rows = rendered.support_files[0].content.strip().splitlines()
    assert rendered_rows[1].startswith("c-ares/asan/parser/seed_001,c-ares,dns,asan,parser,seed_001,4101,agents/")
    assert rendered_rows[-1].startswith("openssl/ubsan/stateful/seed_003,openssl,tls,ubsan,stateful,seed_003,4103,agents/")


def test_bundled_codex_fuzz_catalog_batched_template_is_available():
    assert "codex-fuzz-catalog-batched" in bundled_template_names()
    assert "\nname: codex-fuzz-catalog-batched-128\n" in (
        f"\n{load_bundled_template_yaml('codex-fuzz-catalog-batched')}"
    )
    assert bundled_template_support_files("codex-fuzz-catalog-batched") == ("manifests/codex-fuzz-catalog.csv",)


def test_bundled_codex_fuzz_catalog_batched_template_matches_default_example_files():
    expected_yaml = bundled_template_path("codex-fuzz-catalog-batched").read_text(encoding="utf-8")
    expected_catalog = (
        bundled_template_path("codex-fuzz-catalog-batched").parent / "manifests" / "codex-fuzz-catalog.csv"
    ).read_text(encoding="utf-8")
    rendered = render_bundled_template("codex-fuzz-catalog-batched")

    assert rendered.yaml == expected_yaml
    assert len(rendered.support_files) == 1
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-catalog.csv"
    assert rendered.support_files[0].content == expected_catalog


def test_bundled_codex_fuzz_catalog_batched_template_accepts_overrides_and_renders_support_file(tmp_path):
    rendered = render_bundled_template(
        "codex-fuzz-catalog-batched",
        values={
            "shards": "48",
            "batch_size": "8",
            "concurrency": "12",
            "name": "custom-catalog-batched-48",
            "working_dir": "./custom_catalog_batched",
        },
    )

    assert "name: custom-catalog-batched-48\n" in rendered.yaml
    assert "working_dir: ./custom_catalog_batched\n" in rendered.yaml
    assert "concurrency: 12\n" in rendered.yaml
    assert "values_path: manifests/codex-fuzz-catalog.csv" in rendered.yaml
    assert "batches:" in rendered.yaml
    assert "size: 8" in rendered.yaml
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-catalog.csv"
    rendered_rows = rendered.support_files[0].content.strip().splitlines()
    assert len(rendered_rows) == 49
    assert rendered_rows[0] == "label,target,corpus,sanitizer,focus,bucket,seed,workspace"
    assert rendered_rows[1].startswith("libpng/asan/parser/seed_001,libpng,png,asan,parser,seed_001,4101,agents/")
    assert rendered_rows[-1].startswith(
        "sqlite/ubsan/stateful/seed_003,sqlite,sql,ubsan,stateful,seed_003,4103,agents/"
    )

    pipeline_path = tmp_path / "custom-catalog-batched.yaml"
    pipeline_path.write_text(rendered.yaml, encoding="utf-8")
    support_path = tmp_path / rendered.support_files[0].relative_path
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(rendered.support_files[0].content, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 12
    assert len(pipeline.fanouts["fuzzer"]) == 48
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_47"
    assert pipeline.fanouts["batch_merge"] == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
    ]
    assert pipeline.node_map["fuzzer_00"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["fuzzer_47"].fanout_member["workspace"] == "agents/sqlite_ubsan_seed_003_47"
    assert pipeline.node_map["fuzzer_00"].target.cwd.endswith(
        "custom_catalog_batched/agents/libpng_asan_seed_001_00"
    )
    assert pipeline.node_map["batch_merge_0"].fanout_member["member_ids"] == [
        "fuzzer_00",
        "fuzzer_01",
        "fuzzer_02",
        "fuzzer_03",
        "fuzzer_04",
        "fuzzer_05",
        "fuzzer_06",
        "fuzzer_07",
    ]
    assert pipeline.node_map["merge"].depends_on == pipeline.fanouts["batch_merge"]


def test_bundled_codex_fuzz_catalog_grouped_template_is_available():
    assert "codex-fuzz-catalog-grouped" in bundled_template_names()
    assert "\nname: codex-fuzz-catalog-grouped-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-catalog-grouped')}"
    assert bundled_template_support_files("codex-fuzz-catalog-grouped") == (
        "manifests/codex-fuzz-catalog-grouped.csv",
    )


def test_bundled_codex_fuzz_catalog_grouped_template_matches_default_example_files():
    expected_yaml = bundled_template_path("codex-fuzz-catalog-grouped").read_text(encoding="utf-8")
    expected_catalog = (
        bundled_template_path("codex-fuzz-catalog-grouped").parent / "manifests" / "codex-fuzz-catalog-grouped.csv"
    ).read_text(encoding="utf-8")
    rendered = render_bundled_template("codex-fuzz-catalog-grouped")

    assert rendered.yaml == expected_yaml
    assert len(rendered.support_files) == 1
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-catalog-grouped.csv"
    assert rendered.support_files[0].content == expected_catalog


def test_bundled_codex_fuzz_catalog_grouped_template_accepts_overrides_and_renders_support_file(tmp_path):
    rendered = render_bundled_template(
        "codex-fuzz-catalog-grouped",
        values={
            "shards": "48",
            "concurrency": "12",
            "name": "custom-catalog-grouped-48",
            "working_dir": "./custom_catalog_grouped",
        },
    )

    assert "name: custom-catalog-grouped-48\n" in rendered.yaml
    assert "working_dir: ./custom_catalog_grouped\n" in rendered.yaml
    assert "concurrency: 12\n" in rendered.yaml
    assert "values_path: manifests/codex-fuzz-catalog-grouped.csv" in rendered.yaml
    assert "group_by:" in rendered.yaml
    assert "{{ current.scope.ids | join(\", \") }}" in rendered.yaml
    assert "{{ shard.output }}" in rendered.yaml
    assert rendered.support_files[0].relative_path == "manifests/codex-fuzz-catalog-grouped.csv"
    rendered_rows = rendered.support_files[0].content.strip().splitlines()
    assert len(rendered_rows) == 49
    assert rendered_rows[0] == "label,target,corpus,sanitizer,focus,bucket,seed,workspace"
    assert rendered_rows[1].startswith("libpng/asan/parser/seed_001,libpng,png,asan,parser,seed_001,4101,agents/")
    assert rendered_rows[-1].startswith(
        "sqlite/ubsan/stateful/seed_003,sqlite,sql,ubsan,stateful,seed_003,4103,agents/"
    )

    pipeline_path = tmp_path / "custom-catalog-grouped.yaml"
    pipeline_path.write_text(rendered.yaml, encoding="utf-8")
    support_path = tmp_path / rendered.support_files[0].relative_path
    support_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.write_text(rendered.support_files[0].content, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 12
    assert len(pipeline.fanouts["fuzzer"]) == 48
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_47"
    assert pipeline.fanouts["family_merge"] == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]
    assert pipeline.node_map["fuzzer_00"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["family_merge_0"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["family_merge_0"].fanout_member["member_ids"] == [
        "fuzzer_00",
        "fuzzer_01",
        "fuzzer_02",
        "fuzzer_03",
        "fuzzer_16",
        "fuzzer_17",
        "fuzzer_18",
        "fuzzer_19",
        "fuzzer_32",
        "fuzzer_33",
        "fuzzer_34",
        "fuzzer_35",
    ]
    assert pipeline.node_map["family_merge_0"].depends_on == [
        "fuzzer_00",
        "fuzzer_01",
        "fuzzer_02",
        "fuzzer_03",
        "fuzzer_16",
        "fuzzer_17",
        "fuzzer_18",
        "fuzzer_19",
        "fuzzer_32",
        "fuzzer_33",
        "fuzzer_34",
        "fuzzer_35",
    ]
    assert pipeline.node_map["merge"].depends_on == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]


def test_bundled_codex_fuzz_batched_template_is_available():
    assert "codex-fuzz-batched" in bundled_template_names()
    assert "\nname: codex-fuzz-batched-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-batched')}"


def test_bundled_codex_fuzz_batched_template_matches_default_example_file():
    expected = bundled_template_path("codex-fuzz-batched").read_text(encoding="utf-8")

    assert load_bundled_template_yaml("codex-fuzz-batched") == expected


def test_bundled_codex_fuzz_batched_template_accepts_overrides_and_scopes_batch_dependencies(tmp_path):
    rendered = load_bundled_template_yaml(
        "codex-fuzz-batched",
        values={
            "shards": "48",
            "batch_size": "12",
            "concurrency": "20",
            "name": "custom-fuzz-batched-48",
            "working_dir": "./custom_batched",
        },
    )

    assert "name: custom-fuzz-batched-48\n" in rendered
    assert "working_dir: ./custom_batched\n" in rendered
    assert "concurrency: 20\n" in rendered
    assert "count: 48" in rendered
    assert "size: 12" in rendered
    assert "{{ current.scope.ids | join(\", \") }}" in rendered
    assert "current.scope.with_output.nodes" in rendered
    assert "{{ shard.output }}" in rendered
    assert "Batch reducers needing attention:" in rendered
    assert "{% for batch in fanouts.batch_merge.without_output.nodes %}" in rendered

    pipeline_path = tmp_path / "custom-fuzz-batched.yaml"
    pipeline_path.write_text(rendered, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 20
    assert len(pipeline.fanouts["fuzzer"]) == 48
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_47"
    assert pipeline.node_map["fuzzer_00"].fanout_member["workspace"] == "agents/agent_00"
    assert pipeline.node_map["fuzzer_00"].target.cwd.endswith("custom_batched/agents/agent_00")
    assert pipeline.fanouts["batch_merge"] == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
    ]
    assert pipeline.node_map["batch_merge_0"].fanout_member["member_ids"] == [
        "fuzzer_00",
        "fuzzer_01",
        "fuzzer_02",
        "fuzzer_03",
        "fuzzer_04",
        "fuzzer_05",
        "fuzzer_06",
        "fuzzer_07",
        "fuzzer_08",
        "fuzzer_09",
        "fuzzer_10",
        "fuzzer_11",
    ]
    assert pipeline.node_map["batch_merge_3"].fanout_member["member_ids"] == [
        "fuzzer_36",
        "fuzzer_37",
        "fuzzer_38",
        "fuzzer_39",
        "fuzzer_40",
        "fuzzer_41",
        "fuzzer_42",
        "fuzzer_43",
        "fuzzer_44",
        "fuzzer_45",
        "fuzzer_46",
        "fuzzer_47",
    ]
    assert pipeline.node_map["batch_merge_0"].depends_on == [
        "fuzzer_00",
        "fuzzer_01",
        "fuzzer_02",
        "fuzzer_03",
        "fuzzer_04",
        "fuzzer_05",
        "fuzzer_06",
        "fuzzer_07",
        "fuzzer_08",
        "fuzzer_09",
        "fuzzer_10",
        "fuzzer_11",
    ]
    assert pipeline.node_map["batch_merge_3"].depends_on == [
        "fuzzer_36",
        "fuzzer_37",
        "fuzzer_38",
        "fuzzer_39",
        "fuzzer_40",
        "fuzzer_41",
        "fuzzer_42",
        "fuzzer_43",
        "fuzzer_44",
        "fuzzer_45",
        "fuzzer_46",
        "fuzzer_47",
    ]
    assert pipeline.node_map["merge"].depends_on == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
    ]


def test_bundled_codex_fuzz_swarm_template_is_available():
    assert "codex-fuzz-swarm" in bundled_template_names()
    assert "\nname: codex-fuzz-swarm-32\n" in f"\n{load_bundled_template_yaml('codex-fuzz-swarm')}"


def test_bundled_codex_fuzz_swarm_template_matches_default_example_file():
    expected = bundled_template_path("codex-fuzz-swarm").read_text(encoding="utf-8")

    assert load_bundled_template_yaml("codex-fuzz-swarm") == expected


def test_bundled_codex_fuzz_swarm_template_accepts_overrides_and_preserves_runtime_placeholders(tmp_path):
    rendered = load_bundled_template_yaml(
        "codex-fuzz-swarm",
        values={
            "shards": "128",
            "concurrency": "24",
            "name": "custom-fuzz-128",
            "working_dir": "./custom_swarm",
        },
    )

    assert "name: custom-fuzz-128\n" in rendered
    assert "working_dir: ./custom_swarm\n" in rendered
    assert "concurrency: 24\n" in rendered
    assert "count: 128" in rendered
    assert "{{ shard.number }}" in rendered
    assert "{{ pipeline.working_dir }}" in rendered
    assert "{% for shard in fanouts.fuzzer.nodes %}" in rendered

    pipeline_path = tmp_path / "custom-fuzz.yaml"
    pipeline_path.write_text(rendered, encoding="utf-8")
    pipeline = load_pipeline_from_path(str(pipeline_path))

    assert pipeline.concurrency == 24
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_127"


def test_bundled_codex_fuzz_matrix_pipeline_expands_matrix_fanout_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-matrix")))

    assert pipeline.concurrency == 8
    assert pipeline.fanouts == {
        "fuzzer": ["fuzzer_0", "fuzzer_1", "fuzzer_2", "fuzzer_3", "fuzzer_4", "fuzzer_5", "fuzzer_6", "fuzzer_7"]
    }
    assert [node.id for node in pipeline.nodes[:3]] == ["init", "fuzzer_0", "fuzzer_1"]
    assert pipeline.node_map["fuzzer_0"].prompt.startswith("You are Codex fuzz shard 1 of 8.")
    assert "Target: libpng" in pipeline.node_map["fuzzer_0"].prompt
    assert pipeline.node_map["fuzzer_0"].fanout_member is not None
    assert pipeline.node_map["fuzzer_0"].fanout_member["family"] == {"target": "libpng", "corpus": "png"}
    assert pipeline.node_map["fuzzer_0"].fanout_member["variant"] == {"sanitizer": "asan", "seed": 1101}
    assert pipeline.node_map["fuzzer_0"].target.cwd.endswith("codex_fuzz_matrix/agents/libpng_asan_0")
    assert pipeline.node_map["merge"].depends_on == [
        "fuzzer_0",
        "fuzzer_1",
        "fuzzer_2",
        "fuzzer_3",
        "fuzzer_4",
        "fuzzer_5",
        "fuzzer_6",
        "fuzzer_7",
    ]


def test_bundled_codex_fuzz_matrix_derived_pipeline_expands_derived_member_fields():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-matrix-derived")))

    assert pipeline.concurrency == 8
    assert pipeline.fanouts == {
        "fuzzer": ["fuzzer_0", "fuzzer_1", "fuzzer_2", "fuzzer_3", "fuzzer_4", "fuzzer_5", "fuzzer_6", "fuzzer_7"]
    }
    assert pipeline.node_map["fuzzer_0"].fanout_member is not None
    assert pipeline.node_map["fuzzer_0"].fanout_member["label"] == "libpng/asan/parser/seed-1101"
    assert pipeline.node_map["fuzzer_0"].fanout_member["workspace"] == "agents/libpng_asan_parser_0"
    assert pipeline.node_map["fuzzer_0"].target.cwd.endswith("codex_fuzz_matrix_derived/agents/libpng_asan_parser_0")
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_0"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_7"


def test_bundled_codex_fuzz_matrix_curated_pipeline_expands_curated_member_fields():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-matrix-curated")))

    assert pipeline.concurrency == 8
    assert len(pipeline.fanouts["fuzzer"]) == 14
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_13"
    assert all(
        not (
            node.fanout_member
            and node.fanout_member.get("target") == "sqlite"
            and node.fanout_member.get("focus") == "structure-aware"
        )
        for node in pipeline.nodes
        if node.id.startswith("fuzzer_")
    )
    assert pipeline.node_map["fuzzer_00"].fanout_member["label"] == "libpng / asan / parser / seed_a"
    assert pipeline.node_map["fuzzer_13"].fanout_member["label"] == "openssl / asan / handshake / seed_tls_b"
    assert pipeline.node_map["fuzzer_13"].fanout_member["workspace"] == "agents/openssl_asan_seed_tls_b_13"
    assert pipeline.node_map["fuzzer_13"].target.cwd.endswith("codex_fuzz_matrix_curated/agents/openssl_asan_seed_tls_b_13")
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_00"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_13"


def test_bundled_codex_fuzz_matrix_128_pipeline_expands_into_128_concrete_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-matrix-128")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member is not None
    assert pipeline.node_map["fuzzer_000"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["fuzzer_000"].fanout_member["sanitizer"] == "asan"
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng / asan / parser / seed_a"
    assert pipeline.node_map["fuzzer_000"].fanout_member["workspace"] == "agents/libpng_asan_seed_a_000"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith("codex_fuzz_matrix_128/agents/libpng_asan_seed_a_000")
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_127"


def test_bundled_codex_fuzz_hierarchical_128_pipeline_expands_into_hierarchical_reducers():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-hierarchical-128")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["fuzzer_000"].fanout_member["workspace"] == "agents/libpng_asan_seed_a_000"
    assert len(pipeline.fanouts["family_merge"]) == 4
    assert pipeline.fanouts["family_merge"] == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]
    assert pipeline.node_map["family_merge_0"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["family_merge_3"].fanout_member["target"] == "sqlite"
    assert "current.target" in pipeline.node_map["family_merge_0"].prompt
    assert "current.corpus" in pipeline.node_map["family_merge_0"].prompt
    assert '{% set target = "' not in pipeline.node_map["family_merge_0"].prompt
    assert pipeline.node_map["family_merge_0"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["family_merge_0"].depends_on[-1] == "fuzzer_127"
    assert pipeline.node_map["merge"].depends_on == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]


def test_bundled_codex_fuzz_hierarchical_grouped_pipeline_expands_into_grouped_reducers():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-hierarchical-grouped")))

    assert pipeline.concurrency == 16
    assert len(pipeline.fanouts["fuzzer"]) == 64
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_63"
    assert pipeline.node_map["fuzzer_00"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["fuzzer_00"].fanout_member["workspace"] == "agents/libpng_asan_seed_001_00"
    assert len(pipeline.fanouts["family_merge"]) == 4
    assert pipeline.fanouts["family_merge"] == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]
    assert pipeline.node_map["family_merge_0"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["family_merge_0"].fanout_member["member_ids"] == [
        "fuzzer_00",
        "fuzzer_01",
        "fuzzer_02",
        "fuzzer_03",
        "fuzzer_04",
        "fuzzer_05",
        "fuzzer_06",
        "fuzzer_07",
        "fuzzer_08",
        "fuzzer_09",
        "fuzzer_10",
        "fuzzer_11",
        "fuzzer_12",
        "fuzzer_13",
        "fuzzer_14",
        "fuzzer_15",
    ]
    assert pipeline.node_map["family_merge_3"].fanout_member["target"] == "sqlite"
    assert "current.scope.ids" in pipeline.node_map["family_merge_0"].prompt
    assert "current.scope.with_output.nodes" in pipeline.node_map["family_merge_0"].prompt
    assert "current.target" in pipeline.node_map["family_merge_0"].prompt
    assert "current.corpus" in pipeline.node_map["family_merge_0"].prompt
    assert '{% set target = "' not in pipeline.node_map["family_merge_0"].prompt
    assert pipeline.node_map["family_merge_0"].depends_on[0] == "fuzzer_00"
    assert pipeline.node_map["family_merge_0"].depends_on[-1] == "fuzzer_15"
    assert pipeline.node_map["merge"].depends_on == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]


def test_bundled_codex_fuzz_hierarchical_manifest_pipeline_expands_into_hierarchical_reducers():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-hierarchical-manifest")))

    assert pipeline.concurrency == 16
    assert len(pipeline.fanouts["fuzzer"]) == 64
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_63"
    assert pipeline.node_map["fuzzer_00"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["fuzzer_00"].fanout_member["workspace"] == "agents/libpng_asan_seed_001_00"
    assert len(pipeline.fanouts["family_merge"]) == 4
    assert pipeline.fanouts["family_merge"] == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]
    assert pipeline.node_map["family_merge_0"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["family_merge_3"].fanout_member["target"] == "sqlite"
    assert "current.target" in pipeline.node_map["family_merge_0"].prompt
    assert "current.corpus" in pipeline.node_map["family_merge_0"].prompt
    assert '{% set target = "' not in pipeline.node_map["family_merge_0"].prompt
    assert pipeline.node_map["family_merge_0"].depends_on[0] == "fuzzer_00"
    assert pipeline.node_map["family_merge_0"].depends_on[-1] == "fuzzer_63"
    assert pipeline.node_map["merge"].depends_on == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]


def test_bundled_codex_fuzz_matrix_manifest_pipeline_expands_into_64_concrete_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-matrix-manifest")))

    assert pipeline.concurrency == 16
    assert len(pipeline.fanouts["fuzzer"]) == 64
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_00", "fuzzer_01", "fuzzer_02"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_63"
    assert pipeline.node_map["fuzzer_00"].fanout_member is not None
    assert pipeline.node_map["fuzzer_00"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["fuzzer_00"].fanout_member["sanitizer"] == "asan"
    assert pipeline.node_map["fuzzer_00"].fanout_member["focus"] == "parser"
    assert pipeline.node_map["fuzzer_00"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["fuzzer_00"].fanout_member["workspace"] == "agents/libpng_asan_seed_001_00"
    assert pipeline.node_map["fuzzer_00"].target.cwd.endswith("codex_fuzz_matrix_manifest_64/agents/libpng_asan_seed_001_00")
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_00"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_63"


def test_bundled_codex_fuzz_matrix_manifest_128_pipeline_expands_into_128_concrete_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-matrix-manifest-128")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member is not None
    assert pipeline.node_map["fuzzer_000"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["fuzzer_000"].fanout_member["sanitizer"] == "asan"
    assert pipeline.node_map["fuzzer_000"].fanout_member["focus"] == "parser"
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng/asan/parser/seed_a"
    assert pipeline.node_map["fuzzer_000"].fanout_member["workspace"] == "agents/libpng_asan_seed_a_000"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith(
        "codex_fuzz_matrix_manifest_128/agents/libpng_asan_seed_a_000"
    )
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_127"


def test_bundled_codex_fuzz_browser_128_pipeline_expands_into_128_browser_surface_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-browser-128")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member["target"] == "blink"
    assert pipeline.node_map["fuzzer_000"].fanout_member["corpus"] == "html"
    assert pipeline.node_map["fuzzer_032"].fanout_member["target"] == "v8"
    assert pipeline.node_map["fuzzer_096"].fanout_member["target"] == "libwebp"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith("codex_fuzz_browser_128/agents/blink_asan_seed_001_000")
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_127"


def test_bundled_codex_fuzz_preset_batched_pipeline_expands_into_scoped_batch_reducers():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-preset-batched")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng / asan / parser / seed_001"
    assert pipeline.node_map["fuzzer_032"].fanout_member["target"] == "libjpeg"
    assert pipeline.node_map["fuzzer_127"].fanout_member["bucket"] == "seed_008"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith(
        "codex_fuzz_preset_batched_128/agents/libpng_asan_seed_001_000"
    )
    assert pipeline.fanouts["batch_merge"] == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
        "batch_merge_6",
        "batch_merge_7",
    ]
    assert pipeline.node_map["batch_merge_0"].fanout_member["member_ids"][:3] == [
        "fuzzer_000",
        "fuzzer_001",
        "fuzzer_002",
    ]
    assert pipeline.node_map["batch_merge_7"].fanout_member["member_ids"][-1] == "fuzzer_127"
    assert pipeline.node_map["merge"].depends_on == pipeline.fanouts["batch_merge"]


def test_bundled_codex_fuzz_catalog_pipeline_expands_into_128_concrete_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-catalog")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["fuzzer_000"].fanout_member is not None
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["fuzzer_000"].fanout_member["workspace"] == "agents/libpng_asan_seed_001_000"
    assert pipeline.node_map["fuzzer_127"].fanout_member["bucket"] == "seed_008"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith("codex_fuzz_catalog_128/agents/libpng_asan_seed_001_000")
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_127"


def test_bundled_codex_fuzz_catalog_batched_pipeline_expands_into_scoped_batch_reducers():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-catalog-batched")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.fanouts["batch_merge"] == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
        "batch_merge_6",
        "batch_merge_7",
    ]
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["fuzzer_000"].fanout_member["workspace"] == "agents/libpng_asan_seed_001_000"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith(
        "codex_fuzz_catalog_batched_128/agents/libpng_asan_seed_001_000"
    )
    assert pipeline.node_map["batch_merge_0"].fanout_member["member_ids"] == pipeline.fanouts["fuzzer"][:16]
    assert pipeline.node_map["batch_merge_0"].depends_on == pipeline.fanouts["fuzzer"][:16]
    assert pipeline.node_map["merge"].depends_on == pipeline.fanouts["batch_merge"]


def test_bundled_codex_fuzz_catalog_grouped_pipeline_expands_into_scoped_grouped_reducers():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-catalog-grouped")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert len(pipeline.fanouts["family_merge"]) == 4
    assert pipeline.fanouts["family_merge"] == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]
    assert pipeline.node_map["fuzzer_000"].fanout_member["label"] == "libpng/asan/parser/seed_001"
    assert pipeline.node_map["fuzzer_000"].fanout_member["workspace"] == "agents/libpng_asan_seed_001_000"
    assert pipeline.node_map["fuzzer_000"].target.cwd.endswith(
        "codex_fuzz_catalog_grouped_128/agents/libpng_asan_seed_001_000"
    )
    assert pipeline.node_map["family_merge_0"].fanout_member["target"] == "libpng"
    assert pipeline.node_map["family_merge_0"].fanout_member["member_ids"][:4] == [
        "fuzzer_000",
        "fuzzer_001",
        "fuzzer_002",
        "fuzzer_003",
    ]
    assert pipeline.node_map["family_merge_0"].fanout_member["member_ids"][-4:] == [
        "fuzzer_112",
        "fuzzer_113",
        "fuzzer_114",
        "fuzzer_115",
    ]
    assert "current.scope.ids" in pipeline.node_map["family_merge_0"].prompt
    assert "current.scope.with_output.nodes" in pipeline.node_map["family_merge_0"].prompt
    assert pipeline.node_map["family_merge_0"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["family_merge_0"].depends_on[-1] == "fuzzer_115"
    assert pipeline.node_map["merge"].depends_on == [
        "family_merge_0",
        "family_merge_1",
        "family_merge_2",
        "family_merge_3",
    ]


def test_render_bundled_template_rejects_unknown_fuzz_preset():
    try:
        render_bundled_template("codex-fuzz-matrix-manifest", values={"preset": "missing-preset"})
    except ValueError as exc:
        assert (
            str(exc)
            == "template `codex-fuzz-matrix-manifest` expects `preset` to be one of `oss-fuzz-core`, `browser-surface`, `protocol-stack`, got `missing-preset`"
        )
    else:
        raise AssertionError("expected unknown preset to raise ValueError")


def test_bundled_codex_fanout_repo_sweep_pipeline_expands_into_concrete_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fanout-repo-sweep")))

    assert pipeline.concurrency == 8
    assert pipeline.fanouts == {
        "sweep": ["sweep_0", "sweep_1", "sweep_2", "sweep_3", "sweep_4", "sweep_5", "sweep_6", "sweep_7"]
    }
    assert [node.id for node in pipeline.nodes[:3]] == ["prepare", "sweep_0", "sweep_1"]
    assert pipeline.node_map["merge"].depends_on == [
        "sweep_0",
        "sweep_1",
        "sweep_2",
        "sweep_3",
        "sweep_4",
        "sweep_5",
        "sweep_6",
        "sweep_7",
    ]


def test_bundled_codex_repo_sweep_batched_pipeline_expands_into_batched_reducers():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-repo-sweep-batched")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["sweep"]) == 128
    assert pipeline.fanouts["sweep"][:3] == ["sweep_000", "sweep_001", "sweep_002"]
    assert pipeline.fanouts["sweep"][-1] == "sweep_127"
    assert pipeline.node_map["prepare"].agent == "codex"
    assert pipeline.node_map["prepare"].model == "gpt-5-codex"
    assert pipeline.node_map["prepare"].capture == "final"
    assert pipeline.node_map["prepare"].timeout_seconds == 900
    assert pipeline.node_map["sweep_000"].fanout_member["label"] == "slice 1/128"
    assert pipeline.node_map["sweep_000"].extra_args == ["--search", "-c", 'model_reasoning_effort="high"']
    assert pipeline.fanouts["batch_merge"] == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
        "batch_merge_6",
        "batch_merge_7",
    ]
    assert pipeline.node_map["batch_merge_0"].fanout_member["member_ids"][:3] == [
        "sweep_000",
        "sweep_001",
        "sweep_002",
    ]
    assert pipeline.node_map["batch_merge_0"].fanout_member["member_ids"][-1] == "sweep_015"
    assert pipeline.node_map["batch_merge_7"].fanout_member["member_ids"][0] == "sweep_112"
    assert pipeline.node_map["batch_merge_7"].fanout_member["member_ids"][-1] == "sweep_127"
    assert pipeline.node_map["merge"].depends_on == [
        "batch_merge_0",
        "batch_merge_1",
        "batch_merge_2",
        "batch_merge_3",
        "batch_merge_4",
        "batch_merge_5",
        "batch_merge_6",
        "batch_merge_7",
    ]


def test_bundled_codex_fuzz_swarm_128_template_is_available():
    assert "codex-fuzz-swarm-128" in bundled_template_names()
    assert "\nname: codex-fuzz-swarm-128\n" in f"\n{load_bundled_template_yaml('codex-fuzz-swarm-128')}"


def test_bundled_codex_fuzz_swarm_128_pipeline_expands_into_128_concrete_nodes():
    pipeline = load_pipeline_from_path(str(bundled_template_path("codex-fuzz-swarm-128")))

    assert pipeline.concurrency == 32
    assert len(pipeline.fanouts["fuzzer"]) == 128
    assert pipeline.fanouts["fuzzer"][:3] == ["fuzzer_000", "fuzzer_001", "fuzzer_002"]
    assert pipeline.fanouts["fuzzer"][-1] == "fuzzer_127"
    assert pipeline.node_map["merge"].depends_on[0] == "fuzzer_000"
    assert pipeline.node_map["merge"].depends_on[-1] == "fuzzer_127"


def test_bundled_shell_wrapper_smoke_pipeline_runs_both_agents_in_explicit_shell_wrapper_mode():
    pipeline = load_pipeline_from_path(str(bundled_template_path("local-kimi-shell-wrapper-smoke")))
    codex_node = next(node for node in pipeline.nodes if node.id == "codex_plan")
    claude_node = next(node for node in pipeline.nodes if node.id == "claude_review")

    assert pipeline.concurrency == 2
    assert codex_node.target.kind == "local"
    assert codex_node.target.bootstrap is None
    assert codex_node.target.shell == "bash -lic 'command -v kimi >/dev/null 2>&1 && kimi && {command}'"
    assert codex_node.target.shell_login is False
    assert codex_node.target.shell_interactive is False
    assert codex_node.target.shell_init is None
    assert codex_node.depends_on == []
    assert claude_node.target.bootstrap is None
    assert claude_node.target.shell == "bash -lic 'command -v kimi >/dev/null 2>&1 && kimi && {command}'"
    assert claude_node.target.shell_init is None
    assert claude_node.depends_on == []
