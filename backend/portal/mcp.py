from django.utils import timezone
from mcp_server.djangomcp import MCPToolset
from django.core.mail import send_mail
from datetime import date, datetime, time


class MyAITools(MCPToolset):
    # This method will not be published as a tool because it starts with _

    def create_task(self, title: str, description: str, due: str, priority: str = "standard"):
        """
        Create a task
        :param title:
        :param description:
        :param due: make sure the date is correct
        :param priority:
        :return:
        """
        task = {
            "id": 2323,
            "title": title,
            "description": description,
            "due": due,
            "created": timezone.now().isoformat(),
            "priority": priority,
            "status": "pending"
        }

        return task

    def create_idea(self, title: str, description: str) -> dict:
        """
        Register an idea
        :param title:
        :param description:
        :return:
        """

        idea = {
            "title": title,
            "description": description,
            "created": timezone.now().isoformat(),
        }

        return idea

    def create_note(self, title: str, description: str) -> dict:
        """
        Register a note
        :param title:
        :param description:
        :return:
        """

        note = {
            "title": title,
            "description": description,
            "created": timezone.now().isoformat(),
        }
        return note

    def create_contact(self, fullname: str, phone: str, email: str, company: str) -> dict:
        """
        Create a contact
        :param fullname:
        :param phone:
        :param email:
        :param company:
        :return:
        """
        contact = {
            "fullname": fullname,
            "phone": phone,
            "email": email,
            "company": company,
            "created": timezone.now().isoformat(),
        }

        return contact

    def get_todays_date(self):

        return timezone.now().date().isoformat()

    def get_tasks(self, search_term: str = "") -> list[dict]:

        """
        Lista de tareas filtrada por search_term
        :param search_term:
        :return: list of matching tasks
        """

        lista = [
            {
                "id": 2323,
                "title": "Hacer compras",
                "description": "comprar leche, pan, huevos",
                "due": "30/06/2025",
                "created": "27/06/2025",
                "priority": "standard",
                "status": "pending"
            },
            {
                "id": 2324,
                "title": "Enviar informe",
                "description": "revisar datos de ventas y enviar al equipo",
                "due": "01/07/2025",
                "created": "27/06/2025",
                "priority": "high",
                "status": "in_progress"
            },
            {
                "id": 2325,
                "title": "Llamar a proveedor",
                "description": "confirmar fecha de entrega de materiales",
                "due": "29/06/2025",
                "created": "26/06/2025",
                "priority": "low",
                "status": "completed"
            },
            {
                "id": 2326,
                "title": "Pagar factura de luz",
                "description": "pago correspondiente al mes de mayo",
                "due": "25/06/2025",
                "created": "20/06/2025",
                "priority": "high",
                "status": "overdue"
            },
            {
                "id": 2327,
                "title": "Revisar correos atrasados",
                "description": "responder los correos pendientes de esta semana",
                "due": "26/06/2025",
                "created": "24/06/2025",
                "priority": "standard",
                "status": "overdue"
            },
            {
                "id": 2328,
                "title": "Actualizar documentación",
                "description": "refrescar README y manual de usuario",
                "due": "05/07/2025",
                "created": "26/06/2025",
                "priority": "low",
                "status": "pending"
            },
            {
                "id": 2329,
                "title": "Planificar reunión de proyecto",
                "description": "coordinar fecha y agenda con el equipo",
                "due": "28/06/2025",
                "created": "27/06/2025",
                "priority": "standard",
                "status": "pending"
            }
        ]

        return lista

    def edit_task(self, task_id:int,  title: str="", description: str="", due: str = None, priority: str = "", status: str = ""):

        task = {
                "id": 2324,
                "title": "Enviar informe",
                "description": "revisar datos de ventas y enviar al equipo",
                "due": "01/07/2025",
                "created": "27/06/2025",
                "priority": "high",
                "status": "in_progress"
            }
        if title != "":
            task["title"] = title

        if description != "":
            task["description"] = description

        if due:
            task["due"] = due

        if status != "":
            task["status"] = status

        if priority != "":
            task["priority"] = priority

        return task