from agentflow import DAG, codex, claude

with DAG("ec2-remote-demo", working_dir=".", concurrency=2) as dag:
    scan = codex(
        task_id="scan",
        prompt="Run 'uname -a' and 'cat /etc/os-release' and report what system you are on.",
        tools="read_only",
        target={
            "kind": "ec2",
            "region": "ap-northeast-1",
            "instance_type": "t3.micro",
            "ami": "ami-0d52744d6551d851e",
            "username": "ubuntu",
            "install_agents": ["codex"],
        },
    )
    review = claude(
        task_id="review",
        prompt=(
            "Review the remote system info and suggest what this instance could be used for.\n\n"
            "Remote scan:\n{{ nodes.scan.output }}"
        ),
    )
    scan >> review

print(dag.to_json())
