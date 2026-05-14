from crewai.tools import BaseTool
from notion_client import Client
import os
from dotenv import load_dotenv

load_dotenv()


class NotionCreateCaseTool(BaseTool):
    name: str = "Create Business Case in Notion"
    description: str = """
    Создаёт новую запись (бизнес-кейс) в базе данных Notion.
    Параметры: title, category, use_case, summary, implementation, pros, cons, tools, source, date.
    Инструменты (tools) передаются строкой через запятую.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Используем object.__setattr__ для обхода Pydantic
        object.__setattr__(self, '_notion', Client(auth=os.getenv("NOTION_API_KEY")))
        object.__setattr__(self, '_database_id', "3538cd80a7f480aab786c93e0c370bf5")

    def _run(self, **kwargs) -> str:
        try:
            tools_list = [t.strip() for t in kwargs.get("tools", "").split(",") if t.strip()]
            properties = {
                "Name": {"title": [{"text": {"content": kwargs.get("title", "")}}]},
                "Category": {"select": {"name": kwargs.get("category", "")}},
                "Use Case": {"rich_text": [{"text": {"content": kwargs.get("use_case", "")}}]},
                "Summary": {"rich_text": [{"text": {"content": kwargs.get("summary", "")}}]},
                "Implementation": {"rich_text": [{"text": {"content": kwargs.get("implementation", "")}}]},
                "Pros": {"rich_text": [{"text": {"content": kwargs.get("pros", "")}}]},
                "Cons": {"rich_text": [{"text": {"content": kwargs.get("cons", "")}}]},
                "Source": {"url": kwargs.get("source", "")},
                "Date": {"date": {"start": kwargs.get("date", "")}},
                "Tools": {"multi_select": [{"name": tool} for tool in tools_list]}
            }
            page = self._notion.pages.create(
                parent={"database_id": self._database_id},
                properties=properties
            )
            return f"✅ Кейс «{kwargs.get('title')}» успешно создан в Notion. Ссылка: {page['url']}"
        except Exception as e:
            return f"❌ Ошибка при создании кейса: {e}"


class ScribeAgent:
    def __init__(self):
        self.tool = NotionCreateCaseTool()

    def create_case(self, case_data: dict) -> str:
        return self.tool._run(**case_data)