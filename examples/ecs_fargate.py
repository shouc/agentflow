from agentflow import DAG, codex, claude

with DAG("ecs-fargate-demo", working_dir=".", concurrency=2) as dag:
    task = codex(
        task_id="task",
        prompt="Echo hello from ECS Fargate and list the current directory.",
        target={
            "kind": "ecs",
            "region": "ap-northeast-1",
            "cluster": "agentflow",
            "image": "ubuntu:24.04",
            "subnets": [],
            "security_groups": [],
        },
    )
    review = claude(
        task_id="review",
        prompt="Review: {{ nodes.task.output }}",
    )
    task >> review

print(dag.to_json())
