from crewai.tools import BaseTool
from notion_client import Client
import os
from dotenv import load_dotenv

from logging_config import configure_logging, get_logger

load_dotenv()
configure_logging()
logger = get_logger(__name__)

def build_notion_case_properties(case_data: dict) -> dict:
    tools_list = [t.strip() for t in case_data.get("tools", "").split(",") if t.strip()]
    return {
        "Name": {"title": [{"text": {"content": case_data.get("title", "")}}]},
        "Category": {"select": {"name": case_data.get("category", "")}},
        "Use Case": {"rich_text": [{"text": {"content": case_data.get("use_case", "")}}]},
        "Summary": {"rich_text": [{"text": {"content": case_data.get("summary", "")}}]},
        "Implementation": {"rich_text": [{"text": {"content": case_data.get("implementation", "")}}]},
        "Pros": {"rich_text": [{"text": {"content": case_data.get("pros", "")}}]},
        "Cons": {"rich_text": [{"text": {"content": case_data.get("cons", "")}}]},
        "Source": {"url": case_data.get("source", "")},
        "Date": {"date": {"start": case_data.get("date", "")}},
        "Tools": {"multi_select": [{"name": tool} for tool in tools_list]}
    }


class NotionCreateCaseTool(BaseTool):
    name: str = "Create Business Case in Notion"
    description: str = """
    Создаёт новую запись (бизнес-кейс) в базе данных Notion.
    Параметры: title, category, use_case, summary, implementation, pros, cons, tools, source, date.
    Инструменты (tools) передаются строкой через запятую.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        database_id = os.getenv("NOTION_DATABASE_ID")
        if not database_id:
            raise ValueError("NOTION_DATABASE_ID is required")
        object.__setattr__(self, '_notion', Client(auth=os.getenv("NOTION_API_KEY")))
        object.__setattr__(self, '_database_id', database_id)

    def _run(self, **kwargs) -> str:
        try:
            page = self._notion.pages.create(
                parent={"database_id": self._database_id},
                properties=build_notion_case_properties(kwargs)
            )
            logger.info("notion_case_created", title=kwargs.get("title"))
            return f"✅ Кейс «{kwargs.get('title')}» успешно создан в Notion. Ссылка: {page['url']}"
        except Exception as e:
            logger.exception("notion_case_create_failed", title=kwargs.get("title"))
            return f"❌ Ошибка при создании кейса: {e}"


class ScribeAgent:
    def __init__(self):
        self.tool = NotionCreateCaseTool()

    def create_case(self, case_data: dict) -> str:
        return self.tool._run(**case_data)
