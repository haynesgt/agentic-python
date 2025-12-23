from temporalio import workflow


@workflow.defn
class AgentWorkflow:
    @workflow.run
    async def run(self) -> None:
        pass
