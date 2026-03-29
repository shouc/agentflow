"""ECS Fargate runner for AgentFlow nodes."""

from __future__ import annotations

import asyncio
import time

from agentflow.prepared import ExecutionPaths, PreparedExecution
from agentflow.runners.base import (
    CancelCallback,
    LaunchPlan,
    RawExecutionResult,
    Runner,
    StreamCallback,
)
from agentflow.specs import NodeSpec


class ECSRunner(Runner):
    """Execute agent nodes as ECS Fargate tasks."""

    def _ensure_cluster(self, region: str, cluster_name: str) -> None:
        import boto3

        ecs = boto3.client("ecs", region_name=region)
        try:
            resp = ecs.describe_clusters(clusters=[cluster_name])
            if resp["clusters"] and resp["clusters"][0]["status"] == "ACTIVE":
                return
        except Exception:
            pass
        ecs.create_cluster(clusterName=cluster_name)

    def _ensure_log_group(self, region: str, log_group: str) -> None:
        import boto3

        logs = boto3.client("logs", region_name=region)
        try:
            logs.create_log_group(logGroupName=log_group)
        except logs.exceptions.ResourceAlreadyExistsException:
            pass

    def _ensure_execution_role(self, region: str) -> str:
        import boto3
        import json

        iam = boto3.client("iam")
        role_name = "agentflow-ecs-execution"
        try:
            resp = iam.get_role(RoleName=role_name)
            return resp["Role"]["Arn"]
        except iam.exceptions.NoSuchEntityException:
            pass

        trust = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
        )
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
        )
        # Wait for IAM propagation
        time.sleep(10)
        return resp["Role"]["Arn"]

    def _register_task_def(self, node: NodeSpec, prepared: PreparedExecution, execution_role_arn: str) -> str:
        import boto3

        target = node.target
        ecs = boto3.client("ecs", region_name=target.region)
        image = target.image or "ubuntu:24.04"
        log_group = f"/agentflow/{node.id}"
        env_list = [{"name": k, "value": v} for k, v in prepared.env.items()]
        cmd_str = " ".join(prepared.command)

        resp = ecs.register_task_definition(
            family=f"agentflow-{node.id}",
            networkMode="awsvpc",
            requiresCompatibilities=["FARGATE"],
            cpu=target.cpu,
            memory=target.memory,
            executionRoleArn=execution_role_arn,
            containerDefinitions=[
                {
                    "name": "agent",
                    "image": image,
                    "command": ["bash", "-c", cmd_str],
                    "environment": env_list,
                    "essential": True,
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": log_group,
                            "awslogs-region": target.region,
                            "awslogs-stream-prefix": "agent",
                        },
                    },
                }
            ],
        )
        return resp["taskDefinition"]["taskDefinitionArn"]

    def _run_task(self, node: NodeSpec, task_def_arn: str) -> str:
        import boto3

        target = node.target
        ecs = boto3.client("ecs", region_name=target.region)
        resp = ecs.run_task(
            cluster=target.cluster,
            taskDefinition=task_def_arn,
            launchType="FARGATE",
            count=1,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": target.subnets,
                    "securityGroups": target.security_groups,
                    "assignPublicIp": "ENABLED" if target.assign_public_ip else "DISABLED",
                }
            },
        )
        if resp.get("failures"):
            raise RuntimeError(f"ECS run_task failed: {resp['failures']}")
        return resp["tasks"][0]["taskArn"]

    def _wait_for_task(self, node: NodeSpec, task_arn: str) -> tuple[int, list[str], list[str]]:
        import boto3

        target = node.target
        ecs = boto3.client("ecs", region_name=target.region)
        logs_client = boto3.client("logs", region_name=target.region)
        log_group = f"/agentflow/{node.id}"

        stdout_lines: list[str] = []
        seen_tokens: set[str] = set()

        while True:
            resp = ecs.describe_tasks(cluster=target.cluster, tasks=[task_arn])
            task = resp["tasks"][0]
            status = task["lastStatus"]

            # Stream logs
            try:
                streams = logs_client.describe_log_streams(
                    logGroupName=log_group, orderBy="LastEventTime", limit=10,
                ).get("logStreams", [])
                for stream in streams:
                    events = logs_client.get_log_events(
                        logGroupName=log_group,
                        logStreamName=stream["logStreamName"],
                        startFromHead=True,
                    ).get("events", [])
                    for event in events:
                        token = f"{stream['logStreamName']}:{event['timestamp']}:{event['message']}"
                        if token not in seen_tokens:
                            seen_tokens.add(token)
                            stdout_lines.append(event["message"].rstrip())
            except Exception:
                pass

            if status == "STOPPED":
                container = task.get("containers", [{}])[0]
                exit_code = container.get("exitCode", 1)
                reason = container.get("reason", "")
                stderr_lines = [reason] if reason else []
                return exit_code, stdout_lines, stderr_lines

            time.sleep(5)

    def plan_execution(
        self,
        node: NodeSpec,
        prepared: PreparedExecution,
        paths: ExecutionPaths,
    ) -> LaunchPlan:
        target = node.target
        return LaunchPlan(
            kind="ecs",
            command=prepared.command,
            env=prepared.env,
            cwd=None,
            payload={
                "cluster": target.cluster,
                "image": target.image,
                "region": target.region,
                "cpu": target.cpu,
                "memory": target.memory,
            },
        )

    async def execute(
        self,
        node: NodeSpec,
        prepared: PreparedExecution,
        paths: ExecutionPaths,
        on_output: StreamCallback,
        should_cancel: CancelCallback,
    ) -> RawExecutionResult:
        target = node.target
        if should_cancel():
            return RawExecutionResult(
                exit_code=130, stdout_lines=[], stderr_lines=["Cancelled"],
                timed_out=False, cancelled=True,
            )

        try:
            await on_output("stderr", f"Ensuring ECS cluster {target.cluster}...")
            await asyncio.to_thread(self._ensure_cluster, target.region, target.cluster)

            log_group = f"/agentflow/{node.id}"
            await asyncio.to_thread(self._ensure_log_group, target.region, log_group)

            await on_output("stderr", "Ensuring ECS execution role...")
            role_arn = await asyncio.to_thread(self._ensure_execution_role, target.region)

            await on_output("stderr", "Registering task definition...")
            task_def_arn = await asyncio.to_thread(self._register_task_def, node, prepared, role_arn)

            await on_output("stderr", "Running Fargate task...")
            task_arn = await asyncio.to_thread(self._run_task, node, task_def_arn)
            await on_output("stderr", f"Task {task_arn} started...")

            exit_code, stdout_lines, stderr_lines = await asyncio.to_thread(
                self._wait_for_task, node, task_arn,
            )

            for line in stdout_lines:
                await on_output("stdout", line)
            for line in stderr_lines:
                await on_output("stderr", line)

            return RawExecutionResult(
                exit_code=exit_code,
                stdout_lines=stdout_lines,
                stderr_lines=stderr_lines,
                timed_out=False,
                cancelled=False,
            )
        except Exception as exc:
            return RawExecutionResult(
                exit_code=1, stdout_lines=[],
                stderr_lines=[f"ECS execution failed: {exc}"],
                timed_out=False, cancelled=False,
            )
