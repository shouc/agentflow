from agentflow import DAG, codex_fuzz_campaign


with DAG(
    "airflow-like-fuzz-campaign-helper-128",
    description="Concise Python-authored 128-shard protocol-stack Codex fuzz campaign using the high-level campaign helper.",
    working_dir="./codex_fuzz_python_campaign_helper_128",
    concurrency=32,
    fail_fast=True,
) as dag:
    codex_fuzz_campaign(
        preset="protocol-stack",
        bucket_count=8,
        layout="grouped",
        campaign_label="protocol-stack",
    )

print(dag.to_yaml(), end="")
