"""Built-in data-analysis tool registration for Open WebUI startup."""

from __future__ import annotations

from pathlib import Path

BUILTIN_TOOL_ID = 'builtin:data-analysis'
SYSTEM_USER_ID = 'system'
PUBLIC_READ_GRANT = {'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}


def _get_tool_model_classes():
    from open_webui.models.tools import ToolForm, Tools as ToolsModel

    return ToolForm, ToolsModel


def _get_tool_specs(tool_module) -> list[dict]:
    from open_webui.utils.tools import get_tool_specs

    return get_tool_specs(tool_module)


async def register_builtin_data_analysis_tool(app) -> None:
    """Seed the data-analysis Tools class into DB and warm native caches.

    Open WebUI resolves local tools from the ``tool`` table, then consults
    ``app.state.TOOLS`` and ``app.state.TOOL_CONTENTS``. Both caches are warmed
    here so the live process keeps the instance constructed at startup instead
    of replacing it with a later DB-exec copy on first chat dispatch.
    """
    from open_webui.tools.data_analysis.tool_module import Tools as DataAnalysisTools

    instance = DataAnalysisTools()
    specs = _get_tool_specs(instance)
    source_path = Path(__file__).parent / 'tool_module.py'
    content = source_path.read_text()
    ToolForm, ToolsModel = _get_tool_model_classes()

    form = ToolForm(
        id=BUILTIN_TOOL_ID,
        name='Data Analysis (built-in)',
        content=content,
        meta={
            'description': 'Manufacturing data analysis vertical workspace tools.',
            'manifest': {'builtin': True, 'vertical': 'data-analysis'},
        },
        access_grants=[PUBLIC_READ_GRANT],
    )

    existing = await ToolsModel.get_tool_by_id(BUILTIN_TOOL_ID)
    if existing is None:
        await ToolsModel.insert_new_tool(user_id=SYSTEM_USER_ID, form_data=form, specs=specs)
    else:
        await ToolsModel.update_tool_by_id(
            BUILTIN_TOOL_ID,
            {
                'name': form.name,
                'content': content,
                'specs': specs,
                'meta': form.meta.model_dump(),
                'access_grants': form.access_grants,
            },
        )

    if not hasattr(app.state, 'TOOLS'):
        app.state.TOOLS = {}
    if not hasattr(app.state, 'TOOL_CONTENTS'):
        app.state.TOOL_CONTENTS = {}

    app.state.TOOLS[BUILTIN_TOOL_ID] = instance
    app.state.TOOL_CONTENTS[BUILTIN_TOOL_ID] = content
