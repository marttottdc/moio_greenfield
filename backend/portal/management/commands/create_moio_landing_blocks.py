from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from portal.models import ComponentTemplate, ContentBlock, Tenant


SERVICES_PAGE_HTML = """
<h2>Servicios de Automatización e Inteligencia Artificial</h2>
<p>Ayudamos a pequeñas y medianas empresas B2C a escalar sus operaciones sin incrementar la complejidad. Combinamos estrategia, implementación tecnológica y acompañamiento continuo para que la automatización y la IA trabajen a favor de tu equipo.</p>
<h3>Marketing y Ventas en Automático</h3>
<p>Ponemos tus embudos comerciales a funcionar 24/7. Diseñamos y automatizamos flujos de captación y nutrición de leads, recordatorios de carritos abandonados y comunicaciones personalizadas para impulsar conversiones.</p>
<ul>
  <li>Integración con CRM y herramientas actuales.</li>
  <li>Campañas multicanal con seguimiento en tiempo real.</li>
  <li>Reportes claros para medir cada etapa del embudo.</li>
</ul>
<p><a href="https://moiodigital.com/atraccion-de-clientes-24-7-marketing-y-ventas-en-automatico/" target="_blank" rel="noopener">Conoce cómo automatizamos tus ventas</a></p>
<h3>Atención al Cliente 24/7 con IA</h3>
<p>Implementamos chatbots inteligentes y asistentes conversacionales en WhatsApp, web y redes sociales para resolver consultas frecuentes, derivar solicitudes complejas y mantener a tus clientes informados en todo momento.</p>
<ul>
  <li>Respuestas inmediatas y consistentes.</li>
  <li>Integración con tus sistemas de tickets y órdenes.</li>
  <li>Escalamiento ágil a tu equipo humano cuando se requiere.</li>
</ul>
<p><a href="https://moiodigital.com/cliente-siempre-atendido-atencion-al-cliente-24-7-con-ia/" target="_blank" rel="noopener">Descubre la experiencia de servicio siempre disponible</a></p>
<h3>Administración Automatizada</h3>
<p>Eliminamos tareas operativas repetitivas conectando tus herramientas actuales (ERP, hojas de cálculo, formularios y más). Automatizamos generación de reportes, conciliaciones, actualización de inventario y recordatorios internos.</p>
<ul>
  <li>Procesos confiables sin dependencia de hojas manuales.</li>
  <li>Alertas y notificaciones configuradas a medida.</li>
  <li>Documentación y capacitación para tu equipo.</li>
</ul>
<p><a href="https://moiodigital.com/administracion-automatizada-procesos-internos-eficientes/" target="_blank" rel="noopener">Optimiza la operación interna</a></p>
<h3>Inteligencia de Negocios</h3>
<p>Transformamos tus datos en decisiones accionables. Creamos tableros de BI, modelos predictivos y alertas automáticas para monitorear ventas, demanda y satisfacción del cliente sin requerir un equipo analítico propio.</p>
<ul>
  <li>Modelos y reportes adaptados a tus KPIs.</li>
  <li>Integración con fuentes de datos existentes.</li>
  <li>Acompañamiento para interpretar resultados y tomar acción.</li>
</ul>
<p><a href="https://moiodigital.com/inteligencia-de-negocio-accesible-decisiones-basadas-en-datos-con-ia/" target="_blank" rel="noopener">Explora casos de inteligencia aplicada</a></p>
<h3>Consultoría y Acompañamiento Ejecutivo</h3>
<p>Trabajamos como tu equipo digital extendido. Diagnosticamos oportunidades, priorizamos iniciativas y acompañamos la ejecución con reuniones ejecutivas recurrentes, asegurando que la tecnología sostenga tus objetivos comerciales.</p>
<ul>
  <li>Plan de transformación digital por etapas.</li>
  <li>Coordinación con proveedores y áreas internas.</li>
  <li>Indicadores de seguimiento y mejora continua.</li>
</ul>
<p><a href="https://moiodigital.com/acompanamiento-y-gestion-digital/" target="_blank" rel="noopener">Solicita el acompañamiento integral</a></p>
""".strip()


PRIVACY_PAGE_HTML = """
<h2>Política de Privacidad</h2>
<h4>1. Responsable del tratamiento</h4>
<p>Moio Digital Business Services SAS (en adelante, “la Empresa”), con domicilio en Montevideo, Uruguay, es responsable de la recolección y tratamiento de los datos personales que los usuarios proporcionen a través de su sitio web y servicios asociados.</p>
<p>Para consultas sobre privacidad o para ejercer sus derechos, puede enviar un correo electrónico a <strong><a href="mailto:info@moio.ai" rel="noopener">info@moio.ai</a></strong></p>
<h3>2. Datos personales que se recaban</h3>
<ul>
<li>
<p><strong>Datos de identificación y contacto</strong>: nombre y apellidos, correo electrónico, teléfono (si se solicita), y cualquier otro dato que el usuario decida proporcionar voluntariamente (por ejemplo, al crear una cuenta, suscribirse a un boletín o contactar a la Empresa).</p>
</li>
<li>
<p><strong>Datos de navegación</strong>: dirección IP, tipo de dispositivo, navegador y páginas visitadas, recogidos a través de cookies y tecnologías similares. Estas cookies solo persiguen fines funcionales y analíticos básicos; el usuario puede configurarlas en su navegador.</p>
</li>
<li>
<p><strong>Otros datos</strong>: solo se recabarán datos sensibles (por ejemplo, información de facturación) cuando sea estrictamente necesario para la prestación de servicios y siempre con el consentimiento expreso del usuario.</p>
</li>
</ul>
<p>La Empresa <strong>no</strong> solicita ni almacena datos que no sean necesarios para brindar sus servicios, y mantiene las bases de datos inscritas ante la Unidad Reguladora y de Control de Datos Personales (URCDP) en Uruguay, cumpliendo con las medidas de seguridad adecuadas para garantizar la integridad y confidencialidad de la información<a href="https://www.gub.uy/portal-ejemplo/politica-de-privacidad#:~:text=unasev%2C%20Usted%20consiente%20y%20acepta,garantizan%20su%20integridad%2C%20disponibilidad%20y" rel="noopener" target="_blank">gub.uy</a>.</p>
<h3>3. Finalidad y base legal del tratamiento</h3>
<p>Los datos personales se tratan con las siguientes finalidades:</p>
<ol>
<li>
<p><strong>Prestación de servicios</strong>: registrar y gestionar cuentas de usuario, responder consultas y proporcionar la información solicitada.</p>
</li>
<li>
<p><strong>Comunicación comercial moderada</strong>: enviar boletines o comunicaciones sobre productos y servicios de Moidigital que puedan interesar al usuario. El usuario puede retirarse de estas comunicaciones en cualquier momento.</p>
</li>
<li>
<p><strong>Mejora del sitio y experiencia de usuario</strong>: analizar el uso del sitio web y compilar estadísticas anónimas para optimizar nuestros servicios.</p>
</li>
</ol>
<p>El tratamiento se basa en el consentimiento explícito del usuario y en el principio de finalidad establecido por la Ley Nº 18.331<a href="https://caseguard.com/es/articles/ley-de-proteccion-de-datos-de-caracter-personal-de-uruguay/" rel="noopener" target="_blank">caseguard.com</a>. Moidigital solo utiliza los datos para las finalidades informadas y no los empleará para fines incompatibles sin un nuevo consentimiento.</p>
<h3>4. Transferencia y comunicación de datos</h3>
<ul>
<li>
<p><strong>Internacional</strong>: solo se realizarán transferencias a países u organizaciones que garanticen un nivel adecuado de protección de datos personales conforme a la normativa uruguaya.</p>
</li>
<li>
<p><strong>Proveedores de servicios</strong>: Moio puede utilizar proveedores externos (por ejemplo, servicios de correo electrónico o análisis) para operar su sitio. Estos proveedores actúan como encargados de tratamiento y están contractualmente obligados a cumplir las mismas medidas de seguridad y confidencialidad.</p>
</li>
<li>
<p><strong>Enlaces de terceros</strong>: nuestro sitio puede contener enlaces a sitios externos. La presente política se aplica exclusivamente al sitio de Moidigital y no se extiende a los servicios o contenidos de terceros. Se recomienda leer la política de privacidad de cada sitio externo que visite.</p>
</li>
</ul>
<h3>5. Derechos de los usuarios</h3>
<p>De conformidad con la Ley Nº 18.331, los usuarios tienen derecho a:</p>
<ul>
<li>
<p><strong>Acceso</strong>: obtener información sobre los datos que Moidigital ha recopilado sobre usted.</p>
</li>
<li>
<p><strong>Rectificación</strong>: corregir datos inexactos o incompletos.</p>
</li>
<li>
<p><strong>Actualización e inclusión</strong>: actualizar sus datos o incluir nueva información.</p>
</li>
<li>
<p><strong>Supresión</strong>: solicitar la eliminación de sus datos cuando lo considere pertinente.</p>
</li>
<li>
<p><strong>Oposición</strong>: oponerse al tratamiento de sus datos para fines concretos.</p>
</li>
<li>
<p><strong>Portabilidad</strong>: solicitar que sus datos sean trasladados a otro proveedor, cuando sea técnicamente posible.</p>
</li>
</ul>
<p>Para ejercer estos derechos, el usuario puede contactar a la Empresa por correo electrónico o a través de los medios de contacto indicados en esta política. Moio responderá en un plazo razonable y, en todo caso, dentro de los plazos que establece la normativa.</p>
<h3>6. Medidas de seguridad</h3>
<p>Moidigital adopta medidas técnicas y organizativas razonables para proteger los datos personales contra el acceso no autorizado, pérdida o destrucción. Entre estas medidas se incluyen firewalls, control de accesos, registros de logs y formación en ciberseguridad de su personal. Estas medidas se ajustan a los principios de seguridad, integridad y confidencialidad requeridos por la ley.</p>
<h3>7. Conservación de los datos</h3>
<p>Los datos se conservarán únicamente durante el tiempo necesario para cumplir las finalidades descritas o durante los periodos exigidos por ley. Una vez concluido el plazo de conservación, se adoptarán medidas para anonimizar o eliminar la información.</p>
<h3>8. Cookies y tecnologías similares</h3>
<p>El sitio de Moidigital utiliza cookies mínimas para:</p>
<ul>
<li>
<p>Recordar las preferencias del usuario (por ejemplo, idioma).</p>
</li>
<li>
<p>Obtener estadísticas de tráfico anónimo (Google Analytics o similar).</p>
</li>
</ul>
<p>El usuario puede configurar su navegador para recibir una notificación cuando se instalen cookies o para desactivar su instalación. Si decide no permitir cookies, algunas partes del sitio podrían no funcionar correctamente.</p>
<h3>9. Modificaciones de la política</h3>
<p>Moio puede actualizar esta política de privacidad para reflejar cambios en sus prácticas o en la normativa vigente. Cualquier modificación importante será notificada a través del sitio web. La versión actualizada entrará en vigencia en la fecha de publicación.</p>
<h3>10. Ley aplicable y jurisdicción</h3>
<p>Esta política está regida por las leyes de la República Oriental del Uruguay. Cualquier controversia derivada de su interpretación o ejecución será sometida a los tribunales ordinarios de la ciudad de Montevideo.</p>
<p>MOIO DIGITAL BUSINESS SERVICES SAS – Derechos Reservados 2024</p>
""".strip()


TERMS_PAGE_HTML = """
<h2>Términos y Condiciones de Uso</h2>
<p>Última actualización: octubre 2025</p>
<h3>1. Aceptación</h3>
<p>Al acceder y utilizar los sitios, productos o servicios digitales provistos por Moio Digital Business Services SAS (en adelante, “Moio”), usted acepta cumplir estos Términos y Condiciones y se compromete a utilizarlos de acuerdo con la legislación vigente en la República Oriental del Uruguay.</p>
<h3>2. Descripción de los servicios</h3>
<p>Moio ofrece servicios de consultoría, automatización, inteligencia de negocios y acompañamiento digital orientados a pequeñas y medianas empresas. Cada servicio puede contar con acuerdos específicos de prestación (propuestas comerciales, contratos o anexos) que complementan los presentes términos.</p>
<h3>3. Uso permitido</h3>
<ul>
  <li>El usuario debe proporcionar información veraz y actualizada en los formularios y solicitudes.</li>
  <li>Queda prohibido utilizar los servicios con fines ilegales, ilícitos o que afecten derechos de terceros.</li>
  <li>El acceso a funcionalidades beta o a entornos de prueba podrá estar sujeto a restricciones adicionales comunicadas por Moio.</li>
</ul>
<h3>4. Propiedad intelectual</h3>
<p>Todo el contenido disponible en los sitios y materiales de Moio (textos, diseños, logotipos, procesos, documentación) es propiedad de Moio o se utiliza con autorización. No se permite su reproducción, distribución o modificación sin consentimiento previo por escrito.</p>
<h3>5. Confidencialidad y datos</h3>
<p>Moio se compromete a manejar la información provista por los clientes de forma confidencial y conforme a la <a href="https://moiodigital.com/politica-de-privacidad/" target="_blank" rel="noopener">Política de Privacidad</a>. El cliente se obliga a proteger las credenciales de acceso y a notificar cualquier uso no autorizado.</p>
<h3>6. Limitación de responsabilidad</h3>
<p>Moio no garantiza resultados específicos ni se responsabiliza por daños indirectos, lucro cesante o pérdida de datos que pudieran derivarse del uso de los servicios. La responsabilidad total de Moio frente al cliente no excederá los montos efectivamente pagados por los servicios contratados durante los últimos 12 meses.</p>
<h3>7. Modificaciones</h3>
<p>Moio podrá actualizar estos términos cuando lo considere necesario. Los cambios entrarán en vigencia al momento de su publicación y se comunicarán a los clientes activos mediante los canales habituales (correo electrónico o panel de clientes).</p>
<h3>8. Legislación y jurisdicción</h3>
<p>Estos Términos se rigen por las leyes de la República Oriental del Uruguay. Cualquier controversia se someterá a los tribunales ordinarios de la ciudad de Montevideo.</p>
<h3>9. Contacto</h3>
<p>Para consultas sobre estos términos puede escribir a <a href="mailto:info@moio.ai">info@moio.ai</a> o comunicarse a través de los canales oficiales publicados en el sitio web.</p>
""".strip()


ARTICLE_CARDS = [
    {
        "title": "Acompañamiento y Gestión Digital",
        "excerpt": "Servicio de colaboración continua que integra un director digital externo para guiar la estrategia, la ejecución y la adopción tecnológica del negocio.",
        "href": "https://moiodigital.com/acompanamiento-y-gestion-digital/",
        "date": "29/10/2025",
        "external": True,
    },
    {
        "title": "Consultoría en Automatización y Transformación Digital",
        "excerpt": "Metodología por etapas para diagnosticar procesos, priorizar iniciativas y modernizar la operación con automatizaciones y herramientas emergentes.",
        "href": "https://moiodigital.com/servicios-adicionales-de-consultoria-digital/",
        "date": "27/10/2025",
        "external": True,
    },
    {
        "title": "Inteligencia de Negocios",
        "excerpt": "Implementamos tableros de BI y modelos predictivos que convierten los datos comerciales en decisiones accionables sin depender de un equipo analítico interno.",
        "href": "https://moiodigital.com/inteligencia-de-negocio-accesible-decisiones-basadas-en-datos-con-ia/",
        "date": "27/10/2025",
        "external": True,
    },
    {
        "title": "Administración Automatizada",
        "excerpt": "Automatizamos procesos internos como facturación, inventarios y reportes periódicos conectando las herramientas actuales de la empresa.",
        "href": "https://moiodigital.com/administracion-automatizada-procesos-internos-eficientes/",
        "date": "27/10/2025",
        "external": True,
    },
    {
        "title": "Atención al cliente 24/7 con IA",
        "excerpt": "Chatbots y asistentes conversacionales resuelven consultas frecuentes en todos los canales, liberando a tu equipo y mejorando la experiencia del cliente.",
        "href": "https://moiodigital.com/cliente-siempre-atendido-atencion-al-cliente-24-7-con-ia/",
        "date": "27/10/2025",
        "external": True,
    },
    {
        "title": "Marketing y Ventas en automático",
        "excerpt": "Flujos de comunicación personalizados, campañas multicanal y seguimiento inteligente para generar oportunidades de negocio en piloto automático.",
        "href": "https://moiodigital.com/atraccion-de-clientes-24-7-marketing-y-ventas-en-automatico/",
        "date": "27/10/2025",
        "external": True,
    },
]


TEMPLATES = [
    {
        "slug": "landing-navbar",
        "name": "Landing navigation bar",
        "description": "Top navigation bar for the marketing landing page.",
        "template_path": "portal/partials/landing/navbar.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "brand_url": {"type": "string"},
                "logo": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "alt": {"type": "string"},
                        "height": {"type": ["integer", "string"]},
                    },
                    "required": ["path", "alt", "height"],
                },
                "links": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "href": {"type": "string"},
                            "active": {"type": "boolean"},
                            "external": {"type": "boolean"},
                        },
                        "required": ["label", "href"],
                    },
                },
                "buttons": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "style": {"type": "string"},
                            "href": {"type": "string"},
                            "url_name": {"type": "string"},
                            "external": {"type": "boolean"},
                            "extra_class": {"type": "string"},
                        },
                        "required": ["label", "style"],
                    },
                },
            },
            "required": ["brand_url", "logo", "links", "buttons"],
        },
    },
    {
        "slug": "landing-hero",
        "name": "Landing hero section",
        "description": "Hero headline and illustration.",
        "template_path": "portal/partials/landing/hero.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": ["string", "null"]},
                "headline": {
                    "type": ["object", "null"],
                    "properties": {
                        "static": {"type": ["string", "null"]},
                        "rotating_words": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                        },
                    },
                },
                "eyebrow": {"type": ["string", "null"]},
                "title": {"type": "string"},
                "subtitle": {"type": ["string", "null"]},
                "note": {"type": ["string", "null"]},
                "primary_cta": {
                    "type": ["object", "null"],
                    "properties": {
                        "label": {"type": "string"},
                        "href": {"type": "string"},
                        "icon": {"type": "string"},
                        "style": {"type": "string"},
                        "external": {"type": "boolean"},
                    },
                    "required": ["label", "href"],
                },
                "secondary_cta": {
                    "type": ["object", "null"],
                    "properties": {
                        "label": {"type": "string"},
                        "href": {"type": "string"},
                        "style": {"type": "string"},
                        "external": {"type": "boolean"},
                    },
                    "required": ["label", "href"],
                },
                "illustration": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "alt": {"type": "string"},
                    },
                    "required": ["path", "alt"],
                },
            },
            "required": ["title", "illustration"],
        },
    },
    {
        "slug": "landing-services",
        "name": "Landing service grid",
        "description": "Grid of core functionality cards.",
        "template_path": "portal/partials/landing/services.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "heading": {
                    "type": "object",
                    "properties": {
                        "icon": {"type": ["string", "null"]},
                        "eyebrow": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "subtitle": {"type": ["string", "null"]},
                    },
                    "required": ["title"],
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": ["string", "null"]},
                            "badge": {"type": ["string", "null"]},
                            "href": {"type": ["string", "null"]},
                            "external": {"type": "boolean"},
                            "link_label": {"type": ["string", "null"]},
                            "cta": {
                                "type": ["object", "null"],
                                "properties": {
                                    "label": {"type": "string"},
                                    "href": {"type": "string"},
                                    "external": {"type": "boolean"},
                                },
                                "required": ["label", "href"],
                            },
                        },
                        "required": ["title"],
                    },
                },
                "cta": {
                    "type": ["object", "null"],
                    "properties": {
                        "label": {"type": "string"},
                        "href": {"type": "string"},
                        "style": {"type": "string"},
                        "external": {"type": "boolean"},
                    },
                    "required": ["label", "href"],
                },
            },
            "required": ["section_id", "heading", "items"],
        },
    },
    {
        "slug": "landing-highlights",
        "name": "Landing feature highlights",
        "description": "Detailed feature highlight rows.",
        "template_path": "portal/partials/landing/highlights.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "heading": {
                    "type": ["object", "null"],
                    "properties": {
                        "icon": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "subtitle": {"type": ["string", "null"]},
                    },
                    "required": ["title"],
                },
                "highlights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "image_position": {"enum": ["left", "right"]},
                            "image": {
                                "type": ["object", "null"],
                                "properties": {
                                    "path": {"type": "string"},
                                    "alt": {"type": "string"},
                                },
                                "required": ["path", "alt"],
                            },
                            "eyebrow": {"type": ["string", "null"]},
                            "title": {"type": "string"},
                            "subtitle": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                            "bullets": {
                                "type": ["array", "null"],
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "icon": {"type": ["string", "null"]},
                                        "icon_color": {"type": ["string", "null"]},
                                        "text": {"type": "string"},
                                    },
                                    "required": ["text"],
                                },
                            },
                            "cta": {
                                "type": ["object", "null"],
                                "properties": {
                                    "href": {"type": "string"},
                                    "label": {"type": "string"},
                                    "style": {"type": ["string", "null"]},
                                    "icon": {"type": ["string", "null"]},
                                    "external": {"type": "boolean"},
                                },
                                "required": ["href", "label"],
                            },
                            "add_spacing": {"type": "boolean"},
                        },
                        "required": ["image_position", "title"],
                    },
                },
            },
            "required": ["section_id", "highlights"],
        },
    },
    {
        "slug": "landing-pricing",
        "name": "Landing pricing table",
        "description": "Pricing plan comparison grid.",
        "template_path": "portal/partials/landing/pricing.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "layout": {"type": ["string", "null"]},
                "heading": {
                    "type": "object",
                    "properties": {
                        "icon": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "subtitle": {"type": ["string", "null"]},
                    },
                    "required": ["title"],
                },
                "plans": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "icon": {"type": ["string", "null"]},
                            "price": {"type": "string"},
                            "price_suffix": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                            "features": {
                                "type": ["array", "null"],
                                "items": {"type": "string"},
                            },
                            "recommended": {"type": "boolean"},
                            "badge": {"type": ["string", "null"]},
                            "cta": {
                                "type": ["object", "null"],
                                "properties": {
                                    "href": {"type": "string"},
                                    "label": {"type": "string"},
                                },
                                "required": ["href", "label"],
                            },
                        },
                        "required": ["name", "price"],
                    },
                },
                "posts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": ["string", "null"]},
                            "href": {"type": "string"},
                            "link_label": {"type": ["string", "null"]},
                            "date": {"type": ["string", "null"]},
                            "badge": {"type": ["string", "null"]},
                            "external": {"type": "boolean"},
                        },
                        "required": ["title", "href"],
                    },
                },
                "cta": {
                    "type": ["object", "null"],
                    "properties": {
                        "label": {"type": "string"},
                        "href": {"type": "string"},
                        "style": {"type": "string"},
                        "external": {"type": "boolean"},
                    },
                    "required": ["label", "href"],
                },
            },
            "required": ["section_id", "heading"],
        },
    },
    {
        "slug": "landing-faq",
        "name": "Landing FAQ",
        "description": "Frequently asked questions grid.",
        "template_path": "portal/partials/landing/faq.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "heading": {
                    "type": "object",
                    "properties": {
                        "icon": {"type": "string"},
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                    },
                    "required": ["icon", "title", "subtitle"],
                },
                "columns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "question": {"type": "string"},
                                        "answer": {"type": "string"},
                                    },
                                    "required": ["question", "answer"],
                                },
                            },
                        },
                        "required": ["items"],
                    },
                },
            },
            "required": ["section_id", "heading", "columns"],
        },
    },
    {
        "slug": "landing-contact",
        "name": "Landing contact form",
        "description": "Lead capture form section.",
        "template_path": "portal/partials/landing/contact.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "headline": {
                    "type": ["object", "null"],
                    "properties": {
                        "rotating_words": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                        },
                        "interval": {"type": ["integer", "null"]},
                    },
                },
                "heading": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "subtitle": {"type": ["string", "null"]},
                    },
                    "required": ["title"],
                },
                "description": {"type": ["string", "null"]},
                "cta": {
                    "type": ["object", "null"],
                    "properties": {
                        "label": {"type": "string"},
                        "href": {"type": "string"},
                        "style": {"type": "string"},
                        "external": {"type": "boolean"},
                    },
                    "required": ["label", "href"],
                },
                "benefits": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                },
                "form": {
                    "type": ["object", "null"],
                    "properties": {
                        "action": {"type": "string"},
                        "method": {"type": "string"},
                        "submit_label": {"type": "string"},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "spacing": {"type": ["string", "number"]},
                                    "fields": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "label": {"type": "string"},
                                                "name": {"type": "string"},
                                                "id": {"type": "string"},
                                                "placeholder": {"type": "string"},
                                                "required": {"type": "boolean"},
                                                "column_class": {"type": "string"},
                                                "rows": {"type": ["integer", "null", "string"]},
                                            },
                                            "required": [
                                                "type",
                                                "label",
                                                "name",
                                                "id",
                                                "placeholder",
                                                "required",
                                                "column_class",
                                            ],
                                        },
                                    },
                                },
                                "required": ["spacing", "fields"],
                            },
                        },
                    },
                    "required": ["action", "method", "submit_label", "rows"],
                },
            },
            "required": ["section_id", "heading"],
        },
    },
    {
        "slug": "landing-footer",
        "name": "Landing footer",
        "description": "Marketing site footer.",
        "template_path": "portal/partials/landing/footer.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "brand": {
                    "type": "object",
                    "properties": {
                        "logo": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "alt": {"type": "string"},
                                "height": {"type": ["string", "integer"]},
                            },
                            "required": ["path", "alt", "height"],
                        },
                        "tagline": {"type": "string"},
                    },
                    "required": ["logo", "tagline"],
                },
                "social_links": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "href": {"type": "string"},
                            "icon": {"type": "string"},
                            "external": {"type": "boolean"},
                        },
                        "required": ["href", "icon"],
                    },
                },
                "link_columns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "links": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "href": {"type": "string"},
                                        "external": {"type": "boolean"},
                                    },
                                    "required": ["label", "href"],
                                },
                            },
                        },
                        "required": ["title", "links"],
                    },
                },
                "footer_note": {"type": "string"},
                "smooth_scroll": {"type": "boolean"},
            },
            "required": ["brand", "social_links", "link_columns", "footer_note", "smooth_scroll"],
        },
    },
    {
        "slug": "landing-content-page",
        "name": "Landing content page",
        "description": "Single-column information or legal page.",
        "template_path": "portal/partials/landing/content_page.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": ["string", "null"]},
                "eyebrow": {"type": ["string", "null"]},
                "title": {"type": "string"},
                "subtitle": {"type": ["string", "null"]},
                "updated_on": {"type": ["string", "null"]},
                "content_html": {"type": "string"},
            },
            "required": ["title", "content_html"],
        },
    },
    {
        "slug": "landing-articles",
        "name": "Landing articles grid",
        "description": "Curated article listing for the marketing site.",
        "template_path": "portal/partials/landing/articles.html",
        "context_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "heading": {
                    "type": "object",
                    "properties": {
                        "eyebrow": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "subtitle": {"type": ["string", "null"]},
                    },
                    "required": ["title"],
                },
                "description": {"type": ["string", "null"]},
                "articles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "excerpt": {"type": ["string", "null"]},
                            "href": {"type": "string"},
                            "date": {"type": ["string", "null"]},
                            "external": {"type": "boolean"},
                        },
                        "required": ["title", "href"],
                    },
                },
                "cta": {
                    "type": ["object", "null"],
                    "properties": {
                        "label": {"type": "string"},
                        "href": {"type": "string"},
                        "style": {"type": ["string", "null"]},
                        "external": {"type": "boolean"},
                    },
                    "required": ["label", "href"],
                },
            },
            "required": ["section_id", "heading", "articles"],
        },
    },
]


BLOCKS = [
    {
        "component_slug": "landing-navbar",
        "group": "moio-landing",
        "order": 0,
        "context": {
            "brand_url": "#hero",
            "logo": {
                "path": "images/moio_brand_logo_white.webp",
                "alt": "Moio Digital",
                "height": 40,
            },
            "links": [
                {"label": "Inicio", "href": "#hero", "active": True},
                {"label": "Resultados", "href": "#results"},
                {"label": "Servicios", "href": "#services"},
                {"label": "Actualízate", "href": "#insights"},
                {"label": "Contacto", "href": "#contact"},
            ],
            "buttons": [
                {
                    "label": "WhatsApp",
                    "style": "warning",
                    "href": "https://wa.me/message/BFKQR4A6I4XRG1",
                    "external": True,
                    "extra_class": "fw-semibold text-dark",
                },
                {
                    "label": "Ingresar",
                    "style": "outline-light",
                    "href": "https://app.moio.ai/portal",
                    "external": True,
                },
            ],
        },
    },
    {
        "component_slug": "landing-hero",
        "group": "moio-landing",
        "order": 10,
        "context": {
            "section_id": "hero",
            "headline": {
                "static": "Tu negocio",
                "rotating_words": [
                    "Digitalizado",
                    "Optimizado",
                    "Simplificado",
                ],
            },
            "eyebrow": "Consultoría + Automatización",
            "title": "Impulsa tu Empresa con <span class=\"text-gradient\">Automatización e IA</span>",
            "subtitle": "Diseñamos e implementamos soluciones digitales que mejoran la experiencia de tus clientes y multiplican tus resultados.",
            "note": "Transformamos tus procesos comerciales, operativos y de atención en experiencias fluidas y medibles.",
            "primary_cta": {
                "label": "Quiero saber más",
                "href": "https://wa.me/message/BFKQR4A6I4XRG1",
                "icon": "bi bi-whatsapp",
                "style": "warning",
                "external": True,
            },
            "secondary_cta": {
                "label": "Ver servicios",
                "href": "#services",
                "style": "outline-light",
                "external": False,
            },
            "illustration": {
                "path": "images/landing-hero.jpg",
                "alt": "Consultora revisando su teléfono en una oficina moderna",
            },
        },
    },
    {
        "component_slug": "landing-services",
        "group": "moio-landing",
        "order": 20,
        "context": {
            "section_id": "services",
            "heading": {
                "icon": "bi bi-stars",
                "eyebrow": "Automatización a medida",
                "title": "Servicios que crecen con tu negocio",
                "subtitle": "Ofrecemos una gama de servicios diseñados para digitalizar y optimizar procesos sin importar el tamaño de tu equipo.",
            },
            "items": [
                {
                    "badge": "Automatización",
                    "title": "Marketing y Ventas en automático",
                    "description": "Pon tus esfuerzos comerciales en piloto automático con flujos que capturan, nutren y siguen oportunidades 24/7.",
                    "href": "https://moiodigital.com/atraccion-de-clientes-24-7-marketing-y-ventas-en-automatico/",
                    "external": True,
                    "link_label": "Ver servicio",
                },
                {
                    "badge": "Experiencia",
                    "title": "Atención al cliente 24/7 con IA",
                    "description": "Implementamos chatbots y respuestas inteligentes en tus canales para que cada consulta quede atendida al instante.",
                    "href": "https://moiodigital.com/cliente-siempre-atendido-atencion-al-cliente-24-7-con-ia/",
                    "external": True,
                    "link_label": "Ver servicio",
                },
                {
                    "badge": "Operaciones",
                    "title": "Administración automatizada",
                    "description": "Digitalizamos tareas internas para reducir errores, eliminar planillas manuales y acelerar la gestión diaria.",
                    "href": "https://moiodigital.com/administracion-automatizada-procesos-internos-eficientes/",
                    "external": True,
                    "link_label": "Ver servicio",
                },
                {
                    "badge": "Decisiones",
                    "title": "Inteligencia de Negocios",
                    "description": "Transformamos datos dispersos en reportes automáticos y tableros accionables impulsados por IA.",
                    "href": "https://moiodigital.com/inteligencia-de-negocio-accesible-decisiones-basadas-en-datos-con-ia/",
                    "external": True,
                    "link_label": "Ver servicio",
                },
                {
                    "badge": "Estrategia",
                    "title": "Consultoría en Transformación Digital",
                    "description": "Analizamos tu operación y diseñamos un roadmap de automatización alineado a objetivos concretos.",
                    "href": "https://moiodigital.com/servicios-adicionales-de-consultoria-digital/",
                    "external": True,
                    "link_label": "Ver servicio",
                },
                {
                    "badge": "Acompañamiento",
                    "title": "Gestión Digital Continua",
                    "description": "Nos convertimos en tu mano derecha digital para ejecutar, medir y escalar tus iniciativas tecnológicas.",
                    "href": "https://moiodigital.com/acompanamiento-y-gestion-digital/",
                    "external": True,
                    "link_label": "Ver servicio",
                },
            ],
            "cta": {
                "label": "Ver todos los servicios",
                "href": "https://moiodigital.com/category/servicios/",
                "style": "outline-light",
                "external": True,
            },
        },
    },
    {
        "component_slug": "landing-highlights",
        "group": "moio-landing",
        "order": 30,
        "context": {
            "section_id": "results",
            "heading": None,
            "highlights": [
                {
                    "image_position": "left",
                    "image": {
                        "path": "images/landing-hero.jpg",
                        "alt": "Resultados tangibles para tu empresa",
                    },
                    "eyebrow": "Buscamos Resultados",
                    "title": "Cada servicio está pensado para resolver un dolor específico",
                    "subtitle": "Con impactos concretos en ahorro de tiempo, aumento de ventas y eficiencia operativa.",
                    "bullets": [
                        {"icon": "bi bi-check-circle-fill", "icon_color": "text-warning", "text": "Incremento de ventas"},
                        {"icon": "bi bi-check-circle-fill", "icon_color": "text-warning", "text": "Aumento de la eficiencia del equipo"},
                        {"icon": "bi bi-check-circle-fill", "icon_color": "text-warning", "text": "Mejora en la satisfacción del cliente"},
                        {"icon": "bi bi-check-circle-fill", "icon_color": "text-warning", "text": "Reducción de errores humanos"},
                        {"icon": "bi bi-check-circle-fill", "icon_color": "text-warning", "text": "Mayor visibilidad y control"},
                        {"icon": "bi bi-check-circle-fill", "icon_color": "text-warning", "text": "Alineación entre áreas"},
                        {"icon": "bi bi-check-circle-fill", "icon_color": "text-warning", "text": "Menor impacto del ausentismo"},
                    ],
                    "cta": {
                        "href": "#services",
                        "label": "Explorar servicios",
                        "style": "warning",
                    },
                    "add_spacing": False,
                },
                {
                    "image_position": "right",
                    "image": {
                        "path": "images/landing-insights.jpg",
                        "alt": "Planificación con dashboards y métricas",
                    },
                    "eyebrow": "Comenzá hoy mismo",
                    "title": "Combinamos tecnología, negocio y pasión por la excelencia",
                    "description": "Nos adaptamos a las herramientas que ya usas e integramos tus aplicaciones para que la tecnología trabaje a tu favor.",
                    "cta": {
                        "href": "https://wa.me/message/BFKQR4A6I4XRG1",
                        "label": "Hablemos",
                        "style": "outline-light",
                        "external": True,
                    },
                    "add_spacing": True,
                },
            ],
        },
    },
    {
        "component_slug": "landing-pricing",
        "group": "moio-landing",
        "order": 40,
        "context": {
            "section_id": "insights",
            "layout": "insights",
            "heading": {
                "icon": "bi bi-journal-text",
                "title": "Actualízate",
                "subtitle": "Tómate 15 minutos para descubrir cómo la tecnología puede potenciar tu negocio.",
            },
            "posts": [
                {
                    "title": "¿Por qué falla la adopción de CRM en las PYMES?",
                    "description": "Aprende a evitar los errores más comunes y maximiza el retorno de tu inversión en CRM.",
                    "href": "https://moiodigital.com/por-que-falla-la-adopcion-de-crm-en-las-pymes/",
                    "link_label": "Leer más +",
                    "date": "20/05/2025",
                    "badge": "Blog",
                    "external": True,
                },
                {
                    "title": "Ventajas de usar un CRM en una PYME",
                    "description": "Conoce cómo organizar la información comercial para crecer sin perder cercanía con tus clientes.",
                    "href": "https://moiodigital.com/2910-2/",
                    "link_label": "Leer más +",
                    "date": "20/05/2025",
                    "badge": "Blog",
                    "external": True,
                },
                {
                    "title": "WhatsApp Flows, una poderosa solución ignorada",
                    "description": "Descubre cómo automatizar conversaciones y procesos clave dentro de la plataforma más usada.",
                    "href": "https://moiodigital.com/como-whatsapp-flows-es-una-poderosa-solucion-ignorada/",
                    "link_label": "Leer más +",
                    "badge": "Newsletter",
                    "external": True,
                },
            ],
            "cta": {
                "label": "Ver más artículos",
                "href": "https://moiodigital.com/articulos/",
                "style": "outline-light",
                "external": True,
            },
        },
    },
    {
        "component_slug": "landing-faq",
        "group": "moio-landing",
        "order": 50,
        "context": {
            "section_id": "faq",
            "heading": {
                "icon": "bi bi-question-circle",
                "title": "Preguntas frecuentes",
                "subtitle": "Respondemos las dudas más comunes sobre nuestras soluciones.",
            },
            "columns": [],
        },
        "is_active": False,
    },
    {
        "component_slug": "landing-contact",
        "group": "moio-landing",
        "order": 60,
        "context": {
            "section_id": "contact",
            "headline": {
                "rotating_words": [
                    "Reducir costos",
                    "Mejorar la experiencia de los clientes",
                    "Eliminar errores",
                    "Abrir canales digitales",
                ],
            },
            "heading": {
                "title": "Agenda una consulta sin costo",
                "subtitle": None,
            },
            "description": "Conversemos sobre tu proyecto. Te daremos nuestra opinión con total transparencia y sin compromiso.",
            "cta": {
                "label": "Haz clic aquí",
                "href": "https://wa.me/message/BFKQR4A6I4XRG1",
                "style": "warning",
                "external": True,
            },
            "benefits": [
                "Diagnóstico inicial gratuito",
                "Hoja de ruta adaptada a tus objetivos",
                "Implementación acompañada por especialistas",
            ],
        },
    },
    {
        "component_slug": "landing-footer",
        "group": "moio-landing",
        "order": 70,
        "context": {
            "brand": {
                "logo": {
                    "path": "images/moio_brand_logo_white.png",
                    "alt": "Moio Digital",
                    "height": 60,
                },
                "tagline": "MOIO Digital Business Services SAS",
            },
            "social_links": [
                {
                    "href": "https://www.facebook.com/moiodigital/",
                    "icon": "bi bi-facebook",
                    "external": True,
                },
                {
                    "href": "https://g.co/kgs/2GkJt6p",
                    "icon": "bi bi-google",
                    "external": True,
                },
                {
                    "href": "https://www.instagram.com/moio_digital",
                    "icon": "bi bi-instagram",
                    "external": True,
                },
                {
                    "href": "https://www.linkedin.com/company/moiodigital/",
                    "icon": "bi bi-linkedin",
                    "external": True,
                },
            ],
            "link_columns": [
                {
                    "title": "Empresa",
                    "links": [
                        {"label": "Nosotros", "href": "https://moiodigital.com", "external": True},
                        {"label": "Casos de éxito", "href": "https://moiodigital.com/category/casos/", "external": True},
                        {"label": "Blog", "href": "https://moiodigital.com/articulos/", "external": True},
                    ],
                },
                {
                    "title": "Servicios",
                    "links": [
                        {"label": "Marketing y Ventas", "href": "#services", "external": False},
                        {"label": "Atención con IA", "href": "#services", "external": False},
                        {"label": "Inteligencia de Negocios", "href": "#services", "external": False},
                    ],
                },
                {
                    "title": "Recursos",
                    "links": [
                        {"label": "Política de Privacidad", "href": "https://moiodigital.com/politica-de-privacidad/", "external": True},
                        {"label": "Términos y Condiciones", "href": "https://moiodigital.com/terminos-y-condiciones/", "external": True},
                        {"label": "Centro de ayuda", "href": "https://moiodigital.com/contacto/", "external": True},
                    ],
                },
            ],
            "footer_note": "© 2025 Moio Digital Business Services SAS. Todos los derechos reservados.",
            "smooth_scroll": True,
        },
    },
    {
        "component_slug": "landing-articles",
        "group": "moio-articles",
        "order": 10,
        "title": "Últimos artículos",
        "context": {
            "section_id": "articulos",
            "heading": {
                "eyebrow": "Aprende con Moio",
                "title": "Ideas y estrategias para acelerar tu negocio",
                "subtitle": "Casos reales, guías y buenas prácticas sobre automatización, IA y crecimiento comercial.",
            },
            "description": "Explora nuestra biblioteca de artículos y descubre cómo otras PyMEs implementan soluciones digitales con impacto.",
            "articles": ARTICLE_CARDS,
            "cta": {
                "label": "Ver todos los artículos",
                "href": "https://moiodigital.com/articulos/",
                "style": "outline-light",
                "external": True,
            },
        },
    },
    {
        "component_slug": "landing-content-page",
        "group": "moio-pages-services",
        "order": 10,
        "title": "Servicios",
        "context": {
            "section_id": "servicios",
            "eyebrow": "Qué hacemos",
            "title": "Servicios de Moio Digital",
            "subtitle": "Proyectos llave en mano, automatizaciones a medida y acompañamiento ejecutivo para PYMEs en crecimiento.",
            "updated_on": "Octubre 2025",
            "content_html": SERVICES_PAGE_HTML,
        },
    },
    {
        "component_slug": "landing-content-page",
        "group": "moio-pages-legal",
        "order": 20,
        "title": "Términos y Condiciones",
        "context": {
            "section_id": "terminos",
            "eyebrow": "Aspectos legales",
            "title": "Términos y Condiciones de Uso",
            "subtitle": "Condiciones aplicables al uso de los servicios y activos digitales de Moio Digital.",
            "updated_on": "Octubre 2025",
            "content_html": TERMS_PAGE_HTML,
        },
    },
    {
        "component_slug": "landing-content-page",
        "group": "moio-pages-legal",
        "order": 30,
        "title": "Política de Privacidad",
        "context": {
            "section_id": "privacidad",
            "eyebrow": "Aspectos legales",
            "title": "Política de Privacidad",
            "subtitle": "Conoce cómo protegemos la información que compartes con Moio Digital.",
            "updated_on": "Octubre 2025",
            "content_html": PRIVACY_PAGE_HTML,
        },
    },
]


class Command(BaseCommand):
    help = (
        "Create or update the Moio Digital landing component templates and "
        "content blocks."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-domain",
            default="moiodigital.com",
            help="Tenant domain that should own the landing blocks (default: moiodigital.com).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant_domain: str = options["tenant_domain"]

        tenant, _ = Tenant.objects.get_or_create(
            domain=tenant_domain,
            defaults={
                "nombre": "Moio Digital",
                "enabled": True,
                "tenant_code": uuid.uuid4(),
            },
        )

        components: dict[str, ComponentTemplate] = {}
        for template in TEMPLATES:
            component, _ = ComponentTemplate.objects.update_or_create(
                tenant=tenant,
                slug=template["slug"],
                defaults={
                    "name": template["name"],
                    "description": template["description"],
                    "template_path": template["template_path"],
                    "context_schema": template["context_schema"],
                },
            )
            components[template["slug"]] = component

        for block in BLOCKS:
            component = components[block["component_slug"]]
            ContentBlock.objects.update_or_create(
                tenant=tenant,
                component=component,
                group=block["group"],
                order=block["order"],
                defaults={
                    "title": block.get("title", ""),
                    "context": block.get("context", {}),
                    "is_active": block.get("is_active", True),
                    "visibility": block.get(
                        "visibility", ContentBlock.Visibility.PUBLIC
                    ),
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Landing component templates and content blocks ensured for tenant "
                f"{tenant.domain}."
            )
        )
