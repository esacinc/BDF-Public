from .plotting_agent_workflow import PlottingAgent

agent = PlottingAgent(
                name="PlottingAgent",
                description="Agent responsible for generating Plotly visualizations from other agents' tool outputs.",
                system_prompt=(
                    f"""You are a plotting assistant. You receive parsed tool outputs
                        and a user query and must produce Plotly figures or S3 metadata.
                        If the user requested a specific plot type (violin/box/heatmap/...),
                        you MUST produce that plot type. Validate the produced figure matches the requested type.
                        Return results as a ProcessedOutput containing 'processed_response',
                        'elements' and/or 'graphs'."""
                ),
            )