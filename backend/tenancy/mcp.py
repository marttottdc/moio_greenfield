"""MCP tools for tenancy (tasks, notes, contacts)."""
from django.utils import timezone
from mcp_server.djangomcp import MCPToolset


class MyAITools(MCPToolset):
    def create_task(self, title: str, description: str, due: str, priority: str = "standard"):
        """Create a task."""
        return {
            "id": 2323,
            "title": title,
            "description": description,
            "due": due,
            "created": timezone.now().isoformat(),
            "priority": priority,
            "status": "pending",
        }

    def create_idea(self, title: str, description: str) -> dict:
        """Register an idea."""
        return {"title": title, "description": description, "created": timezone.now().isoformat()}

    def create_note(self, title: str, description: str) -> dict:
        """Register a note."""
        return {"title": title, "description": description, "created": timezone.now().isoformat()}

    def create_contact(self, fullname: str, phone: str, email: str, company: str) -> dict:
        """Create a contact."""
        return {
            "fullname": fullname,
            "phone": phone,
            "email": email,
            "company": company,
            "created": timezone.now().isoformat(),
        }

    def get_todays_date(self):
        return timezone.now().date().isoformat()

    def get_tasks(self, search_term: str = "") -> list[dict]:
        """List tasks filtered by search_term."""
        return [
            {"id": 2323, "title": "Hacer compras", "description": "comprar leche, pan, huevos", "due": "30/06/2025", "created": "27/06/2025", "priority": "standard", "status": "pending"},
            {"id": 2324, "title": "Enviar informe", "description": "revisar datos de ventas", "due": "01/07/2025", "created": "27/06/2025", "priority": "high", "status": "in_progress"},
            {"id": 2325, "title": "Llamar a proveedor", "description": "confirmar fecha de entrega", "due": "29/06/2025", "created": "26/06/2025", "priority": "low", "status": "completed"},
        ]

    def edit_task(self, task_id: int, title: str = "", description: str = "", due: str = None, priority: str = "", status: str = ""):
        task = {"id": 2324, "title": "Enviar informe", "description": "revisar datos", "due": "01/07/2025", "created": "27/06/2025", "priority": "high", "status": "in_progress"}
        if title:
            task["title"] = title
        if description:
            task["description"] = description
        if due:
            task["due"] = due
        if status:
            task["status"] = status
        if priority:
            task["priority"] = priority
        return task
