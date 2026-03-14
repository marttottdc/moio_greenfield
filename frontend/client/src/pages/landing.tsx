import { useState, useRef } from "react";
import { Link, useLocation } from "wouter";
import { motion, useScroll, useTransform, useInView } from "framer-motion";
import {
  Users,
  MessageCircle,
  Workflow,
  Bot,
  BarChart3,
  Calendar,
  Megaphone,
  Plug,
  Shield,
  Zap,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Mail,
  Phone,
  Send,
  Star,
  Lock,
  Loader2,
  Eye,
  EyeOff,
  MousePointer2,
  Smartphone,
  BrainCircuit,
} from "lucide-react";
import moioLogo from "@assets/Moio_New_Logo_Transparent_1764783655330.png";
import ssFlowBuilder from "@assets/screenshot_flow_builder.png";
import ssAutomationStudio from "@assets/screenshot_automation_studio.png";
import ssActivities from "@assets/screenshot_activities.png";
import ssCrmContact from "@assets/screenshot_crm_contact.png";
import mobileContacts from "@assets/mobile_contacts.png";
import mobileCapture from "@assets/mobile_capture.png";
import mobileLinking from "@assets/mobile_linking.png";
import mobileSuggestions from "@assets/mobile_suggestions.png";
import mobileActivities from "@assets/mobile_activities.png";
import { setAccessToken, setRefreshToken, apiV1 } from "@/lib/api";

/* ─── animation variants ─── */
const fadeUp = {
  hidden: { opacity: 0, y: 40 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.7, ease: [0.16, 1, 0.3, 1] },
  }),
};
const stagger = { visible: { transition: { staggerChildren: 0.07 } } };
const scaleIn = {
  hidden: { opacity: 0, scale: 0.92 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] } },
};

/* ─── feature items (grid + carousel) ─── */
const FEATURE_ITEMS = [
  { icon: Users, title: "CRM Inteligente", desc: "Contactos, empresas, deals, pipeline visual, tickets y actividades en un solo lugar.", color: "#58a6ff" },
  { icon: MessageCircle, title: "Chatbot Multicanal", desc: "WhatsApp, Instagram, Messenger, web chat y Shopify con IA conversacional 24/7.", color: "#2ecc71" },
  { icon: Workflow, title: "Automatizaciones", desc: "Editor visual de flujos, triggers por eventos, webhooks, cron y scripts custom.", color: "#ffba08" },
  { icon: Bot, title: "Agent Console", desc: "Asistentes IA con workspaces, skills, plugins y herramientas personalizadas.", color: "#ff6b6b" },
  { icon: BarChart3, title: "Data Lab", desc: "Datasets, análisis, pipelines de importación y paneles de visualización.", color: "#a78bfa" },
  { icon: Calendar, title: "Calendario", desc: "Agendas de equipo, reservas de recursos y disponibilidad pública.", color: "#38bdf8" },
  { icon: Megaphone, title: "Campañas", desc: "Email, WhatsApp, Telegram y SMS con audiencias inteligentes.", color: "#f59e0b" },
  { icon: Plug, title: "Integraciones", desc: "Shopify, WooCommerce, OpenAI, Mercado Pago, Google APIs y más.", color: "#34d399" },
] as const;

/* ─── reusable components ─── */

function AnimatedBlob({ color, size, top, left, delay = 0, duration = 22 }: {
  color: string; size: number; top: string; left: string; delay?: number; duration?: number;
}) {
  return (
    <motion.div
      className="pointer-events-none absolute rounded-full"
      style={{
        width: size, height: size, top, left,
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        filter: `blur(${Math.round(size * 0.45)}px)`,
      }}
      animate={{
        x: [0, 50, -40, 30, 0], y: [0, -45, 35, -20, 0],
        scale: [1, 1.15, 0.88, 1.08, 1], opacity: [0.6, 0.85, 0.5, 0.75, 0.6],
      }}
      transition={{ duration, repeat: Infinity, repeatType: "mirror", ease: "easeInOut", delay }}
    />
  );
}

function Badge({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border border-[#58a6ff]/20 bg-[#58a6ff]/[0.06] px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.15em] text-[#58a6ff] backdrop-blur-sm ${className}`}>
      <Sparkles className="h-3 w-3" />
      {children}
    </span>
  );
}

function GradientBorder({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`relative rounded-2xl p-px ${className}`}>
      <div className="absolute inset-0 rounded-2xl bg-gradient-to-b from-white/[0.12] via-white/[0.04] to-transparent" />
      <div className="relative rounded-2xl bg-[#0c0c14]">
        {children}
      </div>
    </div>
  );
}

function FeaturesCarousel() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const cardWidth = 320;
  const gap = 16;
  const step = cardWidth + gap;
  const items = [...FEATURE_ITEMS, ...FEATURE_ITEMS];

  const scroll = (dir: -1 | 1) => {
    if (!scrollRef.current) return;
    const el = scrollRef.current;
    el.scrollBy({ left: dir * step, behavior: "smooth" });
  };

  return (
    <section className="relative isolate overflow-hidden py-16">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mb-8 text-center">
          <Badge>Todo en una plataforma</Badge>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-white sm:text-3xl">
            CRM, chatbots, automatizaciones e IA
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-gray-500">
            Cada módulo integrado. Sin cambiar de herramienta.
          </p>
        </div>

        <div className="relative">
          <div
            ref={scrollRef}
            className="flex gap-4 overflow-x-auto overflow-y-hidden py-2 pb-4 scroll-smooth scrollbar-hide"
            style={{
              scrollSnapType: "x mandatory",
              WebkitOverflowScrolling: "touch",
            }}
          >
            {items.map(({ icon: Icon, title, desc, color }, i) => (
              <div
                key={`${title}-${i}`}
                className="shrink-0 scroll-snap-start rounded-2xl"
                style={{ width: cardWidth }}
              >
                <GradientBorder className="h-full">
                  <div className="p-6 h-full flex flex-col">
                    <div className="mb-4 inline-flex rounded-xl p-2.5" style={{ backgroundColor: `${color}10` }}>
                      <Icon className="h-5 w-5" style={{ color }} />
                    </div>
                    <h3 className="text-[15px] font-semibold text-white">{title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-gray-500 flex-1">{desc}</p>
                  </div>
                </GradientBorder>
              </div>
            ))}
          </div>

          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => scroll(-1)}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.03] text-gray-400 transition-all hover:border-[#58a6ff]/30 hover:bg-[#58a6ff]/10 hover:text-white"
              aria-label="Anterior"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => scroll(1)}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.03] text-gray-400 transition-all hover:border-[#58a6ff]/30 hover:bg-[#58a6ff]/10 hover:text-white"
              aria-label="Siguiente"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-white/[0.06] last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-4 py-6 text-left text-[15px] font-medium text-white/90 transition-colors hover:text-white"
      >
        <span>{q}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-gray-500 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
      </button>
      <motion.div
        initial={false}
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="overflow-hidden"
      >
        <p className="pb-6 text-sm leading-relaxed text-gray-400">{a}</p>
      </motion.div>
    </div>
  );
}

function slugify(text: string): string {
  return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
}

/* ─── main page ─── */

export default function LandingPage() {
  const [, setLocation] = useLocation();
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const heroY = useTransform(scrollYProgress, [0, 1], [0, 150]);
  const heroScale = useTransform(scrollYProgress, [0, 1], [1, 0.92]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.8], [1, 0]);

  const [enrollForm, setEnrollForm] = useState({ name: "", company: "", email: "", phone: "", password: "", confirmPassword: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const handleEnroll = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFieldErrors({});
    if (enrollForm.password.length < 8) { setFieldErrors({ password: "La contraseña debe tener al menos 8 caracteres." }); return; }
    if (enrollForm.password !== enrollForm.confirmPassword) { setFieldErrors({ confirmPassword: "Las contraseñas no coinciden." }); return; }
    const nameParts = enrollForm.name.trim().split(/\s+/);
    const firstName = nameParts[0] || "";
    const lastName = nameParts.slice(1).join(" ") || "";
    const username = enrollForm.email.split("@")[0].replace(/[^a-zA-Z0-9._-]/g, "");
    const subdomain = slugify(enrollForm.company);
    setSubmitting(true);
    try {
      const res = await fetch(apiV1("/tenants/self-provision/?sync=1"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: enrollForm.company.trim(), email: enrollForm.email.trim(), username, password: enrollForm.password, plan: "free", subdomain: subdomain || undefined, first_name: firstName, last_name: lastName }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (typeof data === "object" && !data.detail) {
          const errors: Record<string, string> = {};
          const fm: Record<string, string> = { nombre: "company", email: "email", username: "email", password: "password", subdomain: "company" };
          for (const [k, v] of Object.entries(data)) { errors[fm[k] || k] = typeof v === "string" ? v : JSON.stringify(v); }
          setFieldErrors(errors);
        } else { setFormError(data.detail || "Error al crear la cuenta. Intentá de nuevo."); }
        return;
      }
      if (data.access_token) { setAccessToken(data.access_token); setRefreshToken(data.refresh_token); setSubmitted(true); setTimeout(() => setLocation("/dashboard"), 1500); }
      else { setSubmitted(true); }
    } catch { setFormError("Error de conexión. Verificá tu internet e intentá de nuevo."); }
    finally { setSubmitting(false); }
  };

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => setEnrollForm(f => ({ ...f, [field]: e.target.value }));
  const inputCls = (err?: string) => `w-full rounded-xl border ${err ? "border-[#ff6b6b]/50" : "border-white/[0.08]"} bg-white/[0.03] px-4 py-3 text-sm text-white placeholder:text-gray-600 outline-none transition-all duration-200 focus:border-[#58a6ff]/40 focus:bg-white/[0.05] focus:ring-1 focus:ring-[#58a6ff]/20`;

  return (
    <div className="relative min-h-screen font-sans text-white antialiased selection:bg-[#58a6ff]/30">
      {/* BG layers */}
      <div className="fixed inset-0 z-0 bg-[#08080d]" />
      <div className="pointer-events-none fixed inset-0 z-[1] overflow-hidden">
        <AnimatedBlob color="rgba(88,166,255,0.12)" size={900} top="-15%" left="0%" delay={0} duration={26} />
        <AnimatedBlob color="rgba(255,186,8,0.07)" size={700} top="30%" left="55%" delay={5} duration={30} />
        <AnimatedBlob color="rgba(46,204,113,0.07)" size={750} top="55%" left="5%" delay={10} duration={28} />
        <AnimatedBlob color="rgba(167,139,250,0.06)" size={600} top="75%" left="50%" delay={7} duration={24} />
      </div>
      {/* Dot grid texture */}
      <div className="pointer-events-none fixed inset-0 z-[1] opacity-[0.03]" style={{ backgroundImage: "radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)", backgroundSize: "32px 32px" }} />

      <div className="relative z-[2]">

      {/* ━━━ NAVBAR ━━━ */}
      <header className="sticky top-0 z-50 border-b border-white/[0.04] bg-[#08080d]/70 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <img src={moioLogo} alt="Moio.ai" className="h-7 w-auto" />
          <nav className="hidden items-center gap-8 text-[13px] font-medium text-gray-500 md:flex">
            {[["#features", "Producto"], ["#showcase", "Plataforma"], ["#pricing", "Precios"], ["#faq", "FAQ"]].map(([href, label]) => (
              <a key={href} href={href} className="transition-colors duration-200 hover:text-white">{label}</a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <Link href="/login" className="rounded-lg px-4 py-2 text-[13px] font-medium text-gray-400 transition-colors hover:text-white">Iniciar sesión</Link>
            <a href="#registro" className="rounded-lg bg-white px-4 py-2 text-[13px] font-semibold text-[#08080d] transition-all hover:bg-gray-100">Probar gratis</a>
          </div>
        </div>
      </header>

      {/* ━━━ HERO ━━━ */}
      <section ref={heroRef} className="relative isolate overflow-hidden pb-8 pt-16 md:pt-24">
        <div className="mx-auto max-w-7xl px-6">
          <motion.div initial="hidden" animate="visible" variants={stagger} className="mx-auto max-w-[52rem] text-center">
            <motion.div variants={fadeUp} custom={0}>
              <Badge>Plataforma SaaS todo-en-uno</Badge>
            </motion.div>
            <motion.h1 variants={fadeUp} custom={1} className="mt-8 text-[clamp(2.25rem,5.5vw,4.5rem)] font-extrabold leading-[1.08] tracking-[-0.03em]">
              <span className="bg-gradient-to-r from-[#58a6ff] via-[#7dd3fc] to-[#2ecc71] bg-clip-text text-transparent">Moio.ai</span> — CRM, chatbots y<br />
              automatizaciones con IA
            </motion.h1>
            <motion.p variants={fadeUp} custom={2} className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-gray-400">
              Gestiona clientes, automatiza procesos y potencia tu equipo con inteligencia artificial. Todo conectado en Moio.ai.
            </motion.p>
            <motion.div variants={fadeUp} custom={3} className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <a href="#registro" className="group relative flex items-center gap-2.5 overflow-hidden rounded-xl bg-[#58a6ff] px-8 py-4 text-[15px] font-semibold text-white transition-all hover:shadow-[0_0_40px_rgba(88,166,255,0.3)]">
                <span className="relative z-10 flex items-center gap-2.5">
                  Empezar gratis — 5 usuarios
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-[#58a6ff] to-[#3b82f6] opacity-0 transition-opacity group-hover:opacity-100" />
              </a>
              <a href="#showcase" className="flex items-center gap-2 rounded-xl border border-white/[0.08] px-8 py-4 text-[15px] font-medium text-gray-400 transition-all hover:border-white/15 hover:text-white">
                <MousePointer2 className="h-4 w-4" /> Ver la plataforma
              </a>
            </motion.div>
            <motion.p variants={fadeUp} custom={4} className="mt-5 text-[13px] text-gray-600">
              Sin tarjeta de crédito &bull; Setup en 30 segundos &bull; CRM gratis 12 meses
            </motion.p>
          </motion.div>

          {/* Hero product shot */}
          <motion.div style={{ y: heroY, scale: heroScale, opacity: heroOpacity }} className="relative mx-auto mt-16 max-w-6xl">
            <motion.div initial={{ opacity: 0, y: 60 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5, duration: 1, ease: [0.16, 1, 0.3, 1] }}>
              {/* Glow underneath */}
              <div className="absolute -bottom-12 left-1/2 h-[200px] w-[80%] -translate-x-1/2 rounded-full bg-[#58a6ff]/15 blur-[80px]" />
              <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0c0c14] shadow-[0_32px_100px_-20px_rgba(0,0,0,0.8)]" style={{ perspective: "1200px" }}>
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#58a6ff]/40 to-transparent" />
                <img src={ssFlowBuilder} alt="Moio.ai — Editor Visual de Flujos" className="w-full" />
              </div>
              {/* Floating mobile phone overlay */}
              <motion.div
                initial={{ opacity: 0, y: 30, x: 10 }}
                animate={{ opacity: 1, y: 0, x: 0 }}
                transition={{ delay: 1, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="absolute -bottom-8 -right-4 hidden md:block lg:-right-8"
              >
                <div className="relative overflow-hidden rounded-[1.5rem] border-[3px] border-white/15 bg-black shadow-[0_20px_80px_-10px_rgba(0,0,0,0.9)]">
                  <div className="absolute left-1/2 top-0 z-10 h-5 w-20 -translate-x-1/2 rounded-b-xl bg-black" />
                  <img src={mobileActivities} alt="Moio.ai móvil" className="w-[160px] lg:w-[180px]" />
                </div>
              </motion.div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ━━━ LOGOS / TRUST ━━━ */}
      <section className="border-y border-white/[0.04] py-10">
        <div className="mx-auto max-w-5xl px-6">
          <p className="mb-6 text-center text-[11px] font-semibold uppercase tracking-[0.2em] text-gray-600">Integrado con las herramientas que ya usás</p>
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
            {["WhatsApp Business", "Shopify", "OpenAI", "Instagram", "Mercado Pago", "WooCommerce", "Google APIs"].map(name => (
              <span key={name} className="text-[13px] font-medium text-gray-600 transition-colors hover:text-gray-400">{name}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ━━━ FEATURES CAROUSEL ━━━ */}
      <FeaturesCarousel />

      {/* ━━━ STATS ━━━ */}
      <section className="mx-auto max-w-5xl px-6 py-20">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-80px" }} variants={stagger} className="grid grid-cols-2 gap-6 md:grid-cols-4">
          {([
            { value: "8+", label: "Módulos integrados", color: "#58a6ff" },
            { value: "6", label: "Canales de chat", color: "#2ecc71" },
            { value: "24/7", label: "IA operando", color: "#ffba08" },
            { value: "<1min", label: "Para crear tu cuenta", color: "#a78bfa" },
          ] as const).map(({ value, label, color }, i) => (
            <motion.div key={label} variants={fadeUp} custom={i} className="text-center">
              <p className="text-3xl font-bold tracking-tight md:text-4xl" style={{ color }}>{value}</p>
              <p className="mt-1.5 text-[13px] text-gray-500">{label}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ━━━ FEATURES ━━━ */}
      <section id="features" className="relative isolate mx-auto max-w-7xl px-6 py-32">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-100px" }} variants={stagger} className="text-center">
          <motion.div variants={fadeUp} custom={0}><Badge>Funcionalidades</Badge></motion.div>
          <motion.h2 variants={fadeUp} custom={1} className="mt-5 text-3xl font-bold tracking-tight sm:text-[2.75rem] sm:leading-[1.15]">
            Cada módulo que tu negocio necesita.<br />
            <span className="text-gray-500">Integrados. Inteligentes. Listos.</span>
          </motion.h2>
        </motion.div>

        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-50px" }} variants={stagger} className="mt-20 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURE_ITEMS.map(({ icon: Icon, title, desc, color }) => (
            <motion.div key={title} variants={fadeUp} whileHover={{ scale: 1.03 }} transition={{ type: "spring", stiffness: 400, damping: 25 }}>
              <GradientBorder>
                <div className="p-6">
                  <div className="mb-4 inline-flex rounded-xl p-2.5" style={{ backgroundColor: `${color}10` }}>
                    <Icon className="h-5 w-5" style={{ color }} />
                  </div>
                  <h3 className="text-[15px] font-semibold text-white">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-gray-500">{desc}</p>
                </div>
              </GradientBorder>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ━━━ PRODUCT SHOWCASE ━━━ */}
      <section id="showcase" className="relative isolate mx-auto max-w-7xl px-6 py-32">
        <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
          <AnimatedBlob color="rgba(88,166,255,0.06)" size={500} top="5%" left="70%" delay={1} duration={24} />
        </div>
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-100px" }} variants={stagger} className="text-center">
          <motion.div variants={fadeUp} custom={0}><Badge>La plataforma por dentro</Badge></motion.div>
          <motion.h2 variants={fadeUp} custom={1} className="mt-5 text-3xl font-bold tracking-tight sm:text-[2.75rem] sm:leading-[1.15]">
            Diseñada para que{" "}<span className="bg-gradient-to-r from-[#58a6ff] to-[#2ecc71] bg-clip-text text-transparent">todo fluya</span>
          </motion.h2>
          <motion.p variants={fadeUp} custom={2} className="mx-auto mt-4 max-w-lg text-gray-500">
            Interfaz moderna e intuitiva. Cada módulo conectado, cada dato accesible.
          </motion.p>
        </motion.div>

        <div className="mt-20 space-y-4">
          {/* Row 1: CRM + Automation Studio */}
          <div className="grid gap-4 md:grid-cols-5">
            <ShowcaseCard className="md:col-span-3" icon={Users} color="#58a6ff" title="CRM y Contactos" desc="Timeline completa, negocios, mensajes y datos de cada contacto." img={ssCrmContact} />
            <ShowcaseCard className="md:col-span-2" icon={Zap} color="#2ecc71" title="Automation Studio" desc="Scripts, webhooks, agentes y campañas en un panel." img={ssAutomationStudio} />
          </div>
          {/* Row 2: Activities + Mobile capture */}
          <div className="grid gap-4 md:grid-cols-5">
            <ShowcaseCard className="md:col-span-2" icon={BrainCircuit} color="#a78bfa" title="Captura con IA" desc="Dictá lo que pasó y la IA crea actividades, tareas y follow-ups." img={mobileLinking} isMobile />
            <ShowcaseCard className="md:col-span-3" icon={Calendar} color="#ff6b6b" title="Actividades y Calendario" desc="Tareas, notas, ideas y eventos con vista calendario integrada." img={ssActivities} />
          </div>
        </div>
      </section>

      {/* ━━━ MOBILE EXPERIENCE ━━━ */}
      <section className="relative isolate overflow-hidden py-32">
        <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
          <AnimatedBlob color="rgba(46,204,113,0.06)" size={600} top="20%" left="-10%" delay={3} duration={26} />
          <AnimatedBlob color="rgba(88,166,255,0.05)" size={500} top="50%" left="80%" delay={7} duration={22} />
        </div>
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid items-center gap-16 lg:grid-cols-2">
            {/* Left: copy */}
            <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-100px" }} variants={stagger}>
              <motion.div variants={fadeUp} custom={0}><Badge>Experiencia móvil</Badge></motion.div>
              <motion.h2 variants={fadeUp} custom={1} className="mt-5 text-3xl font-bold tracking-tight sm:text-[2.75rem] sm:leading-[1.15]">
                Tu CRM en el{" "}<span className="bg-gradient-to-r from-[#58a6ff] to-[#a78bfa] bg-clip-text text-transparent">bolsillo</span>
              </motion.h2>
              <motion.p variants={fadeUp} custom={2} className="mt-5 max-w-md text-gray-500 leading-relaxed">
                Moio.ai funciona como una PWA nativa en tu celular. Registrá actividades con lenguaje natural, gestioná contactos y recibí sugerencias de la IA — todo desde el teléfono.
              </motion.p>
              <motion.div variants={fadeUp} custom={3} className="mt-10 space-y-5">
                {([
                  { icon: BrainCircuit, color: "#58a6ff", title: "Captura inteligente", desc: "Escribí lo que pasó en lenguaje natural. La IA extrae contactos, tareas y eventos." },
                  { icon: Users, color: "#2ecc71", title: "CRM completo", desc: "Contactos, cuentas y actividades accesibles desde cualquier lugar." },
                  { icon: Sparkles, color: "#ffba08", title: "Sugerencias IA", desc: "Recibí follow-ups y acciones sugeridas automáticamente tras cada interacción." },
                ] as const).map(({ icon: Icon, color, title, desc }) => (
                  <div key={title} className="flex gap-4">
                    <div className="mt-0.5 shrink-0 rounded-lg p-2" style={{ backgroundColor: `${color}10` }}>
                      <Icon className="h-4 w-4" style={{ color }} />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-white">{title}</h4>
                      <p className="mt-1 text-sm text-gray-500">{desc}</p>
                    </div>
                  </div>
                ))}
              </motion.div>
            </motion.div>

            {/* Right: phone lineup */}
            <motion.div
              initial={{ opacity: 0, x: 40 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className="relative flex items-end justify-center gap-4 md:gap-5"
            >
              {/* Glow behind phones */}
              <div className="pointer-events-none absolute left-1/2 top-1/2 h-[400px] w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#58a6ff]/10 blur-[100px]" />

              <PhoneFrame img={mobileContacts} alt="Contactos" delay={0} className="-mb-8 hidden sm:block" />
              <PhoneFrame img={mobileCapture} alt="Captura IA" delay={0.15} className="z-10 scale-105" featured />
              <PhoneFrame img={mobileSuggestions} alt="Sugerencias" delay={0.3} className="-mb-8 hidden sm:block" />
            </motion.div>
          </div>
        </div>
      </section>

      {/* ━━━ HOW IT WORKS ━━━ */}
      <section className="relative isolate mx-auto max-w-5xl px-6 py-32">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-100px" }} variants={stagger} className="text-center">
          <motion.div variants={fadeUp} custom={0}><Badge>Cómo funciona</Badge></motion.div>
          <motion.h2 variants={fadeUp} custom={1} className="mt-5 text-3xl font-bold tracking-tight sm:text-[2.75rem] sm:leading-[1.15]">
            Arrancá en <span className="text-[#2ecc71]">minutos</span>, no en semanas
          </motion.h2>
        </motion.div>

        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-50px" }} variants={stagger} className="mt-20 grid gap-6 md:grid-cols-3">
          {([
            { n: "01", title: "Creá tu cuenta", desc: "Registrate gratis en 30 segundos. 5 usuarios CRM sin costo por 12 meses.", color: "#58a6ff" },
            { n: "02", title: "Conectá tus canales", desc: "WhatsApp, Instagram, tu e-commerce y las herramientas que ya usás.", color: "#ffba08" },
            { n: "03", title: "Automatizá y crecé", desc: "Activá chatbots, flujos automáticos y agentes IA. La plataforma trabaja por vos.", color: "#2ecc71" },
          ] as const).map(({ n, title, desc, color }) => (
            <motion.div key={n} variants={fadeUp}>
              <GradientBorder>
                <div className="p-8">
                  <span className="text-6xl font-black leading-none" style={{ color, opacity: 0.1 }}>{n}</span>
                  <h3 className="mt-3 text-lg font-semibold text-white">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-gray-500">{desc}</p>
                </div>
              </GradientBorder>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ━━━ PRICING ━━━ */}
      <section id="pricing" className="relative isolate mx-auto max-w-7xl px-6 py-32">
        <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
          <AnimatedBlob color="rgba(167,139,250,0.07)" size={500} top="10%" left="-10%" delay={3} duration={26} />
        </div>
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-100px" }} variants={stagger} className="text-center">
          <motion.div variants={fadeUp} custom={0}><Badge>Precios</Badge></motion.div>
          <motion.h2 variants={fadeUp} custom={1} className="mt-5 text-3xl font-bold tracking-tight sm:text-[2.75rem] sm:leading-[1.15]">
            Planes simples.{" "}<span className="text-[#ffba08]">Sin sorpresas.</span>
          </motion.h2>
          <motion.p variants={fadeUp} custom={2} className="mx-auto mt-4 max-w-lg text-gray-500">
            Empezá gratis con el CRM y sumá módulos cuando los necesites.
          </motion.p>
        </motion.div>

        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-50px" }} variants={stagger} className="mt-20 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          <PricingCard title="CRM" price="$15" unit="USD/usuario/mes" desc="Gestión completa de clientes, ventas y soporte." badge="5 gratis x 12 meses" highlight features={["Contactos ilimitados", "Pipeline visual", "Tickets y soporte", "Actividades y calendario", "Productos y catálogo", "API completa"]} ctaText="Empezar gratis" />
          <PricingCard title="Automatizaciones" price="$100" unit="USD/mes" desc="Automatizá procesos sin código." features={["Editor visual de flujos", "Webhooks, cron, eventos", "Scripts custom", "Campañas multicanal", "Logs en tiempo real", "MCP e integraciones"]} />
          <PricingCard title="Chatbot" price="$100" unit="USD/mes" desc="Atención automatizada multicanal." features={["WhatsApp Business API", "Instagram y Messenger", "Chat web y Shopify", "IA con GPT-4o", "Memoria de sesiones", "Routing inteligente"]} />
          <PricingCard title="Agent Console" price="$40" unit="USD/usuario/mes" desc="Asistentes IA para tu equipo." features={["Workspaces custom", "Skills y plugins IA", "Herramientas propias", "Automatizaciones", "Modelos OpenAI", "Historial completo"]} />
        </motion.div>
        <p className="mt-10 text-center text-[13px] text-gray-600">
          Facturación mensual en USD. Descuentos por plan anual.
        </p>
      </section>

      {/* ━━━ TESTIMONIALS ━━━ */}
      <section className="mx-auto max-w-7xl px-6 py-24">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-80px" }} variants={stagger} className="grid gap-5 md:grid-cols-2">
          <motion.div variants={scaleIn}>
            <GradientBorder className="h-full">
              <div className="flex h-full flex-col justify-between p-10 md:p-12">
                <div>
                  <div className="mb-5 flex items-center gap-1">
                    {[...Array(5)].map((_, i) => <Star key={i} className="h-3.5 w-3.5 fill-[#ffba08] text-[#ffba08]" />)}
                  </div>
                  <blockquote className="text-lg font-medium leading-relaxed text-gray-200">
                    "Moio.ai nos permitió centralizar clientes, mensajes, automatizaciones y reportes. Es como tener un equipo extra trabajando 24/7."
                  </blockquote>
                </div>
                <p className="mt-6 text-sm text-gray-600">— Equipo de early adopters, 2025</p>
              </div>
            </GradientBorder>
          </motion.div>
          <motion.div variants={scaleIn}>
            <GradientBorder className="h-full">
              <div className="flex h-full flex-col justify-between p-10 md:p-12">
                <div>
                  <div className="mb-5 flex items-center gap-1">
                    {[...Array(5)].map((_, i) => <Star key={i} className="h-3.5 w-3.5 fill-[#ffba08] text-[#ffba08]" />)}
                  </div>
                  <blockquote className="text-lg font-medium leading-relaxed text-gray-200">
                    "La captura de actividades desde el celular con IA es increíble. Hablo con un cliente, lo registro en 10 segundos y el sistema sugiere los follow-ups."
                  </blockquote>
                </div>
                <div className="mt-6 flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#58a6ff]/10">
                    <Smartphone className="h-3.5 w-3.5 text-[#58a6ff]" />
                  </div>
                  <p className="text-sm text-gray-600">— Usuario PWA móvil, 2026</p>
                </div>
              </div>
            </GradientBorder>
          </motion.div>
        </motion.div>
      </section>

      {/* ━━━ ENROLL ━━━ */}
      <section id="registro" className="mx-auto max-w-7xl px-6 py-32">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-100px" }} variants={stagger} className="mx-auto max-w-2xl">
          <motion.div variants={fadeUp} custom={0} className="text-center"><Badge>Comenzá hoy</Badge></motion.div>
          <motion.h2 variants={fadeUp} custom={1} className="mt-5 text-center text-3xl font-bold tracking-tight sm:text-[2.75rem] sm:leading-[1.15]">
            Activá tu cuenta{" "}<span className="text-[#2ecc71]">gratis</span>
          </motion.h2>
          <motion.p variants={fadeUp} custom={2} className="mt-4 text-center text-gray-500">
            5 usuarios CRM sin costo por 12 meses. Sin tarjeta. Sin compromiso.
          </motion.p>

          {submitted ? (
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="mt-14">
              <GradientBorder>
                <div className="p-12 text-center">
                  <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-[#2ecc71]/10"><Check className="h-8 w-8 text-[#2ecc71]" /></div>
                  <h3 className="text-2xl font-bold text-white">¡Tu plataforma está lista!</h3>
                  <p className="mt-3 text-gray-400">Redirigiendo al dashboard...</p>
                  <Loader2 className="mx-auto mt-5 h-5 w-5 animate-spin text-[#2ecc71]" />
                </div>
              </GradientBorder>
            </motion.div>
          ) : (
            <motion.div variants={fadeUp} custom={3} className="mt-14">
              <GradientBorder>
                <form onSubmit={handleEnroll} className="space-y-5 p-8 md:p-10">
                  {formError && <div className="rounded-xl border border-[#ff6b6b]/20 bg-[#ff6b6b]/5 px-4 py-3 text-sm text-[#ff6b6b]">{formError}</div>}

                  <div className="grid gap-5 sm:grid-cols-2">
                    <FormField label="Nombre completo"><input required type="text" value={enrollForm.name} onChange={set("name")} placeholder="Tu nombre" className={inputCls()} /></FormField>
                    <FormField label="Empresa" error={fieldErrors.company}><input required type="text" value={enrollForm.company} onChange={set("company")} placeholder="Nombre de tu empresa" className={inputCls(fieldErrors.company)} /></FormField>
                  </div>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <FormField label="Email" error={fieldErrors.email}>
                      <div className="relative"><Mail className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-600" /><input required type="email" value={enrollForm.email} onChange={set("email")} placeholder="tu@empresa.com" className={`${inputCls(fieldErrors.email)} pl-10`} /></div>
                    </FormField>
                    <FormField label={<>Teléfono <span className="text-gray-700">(opcional)</span></>}>
                      <div className="relative"><Phone className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-600" /><input type="tel" value={enrollForm.phone} onChange={set("phone")} placeholder="+54 11 1234-5678" className={`${inputCls()} pl-10`} /></div>
                    </FormField>
                  </div>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <FormField label="Contraseña" error={fieldErrors.password}>
                      <div className="relative">
                        <Lock className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-600" />
                        <input required type={showPassword ? "text" : "password"} value={enrollForm.password} onChange={set("password")} placeholder="Mínimo 8 caracteres" className={`${inputCls(fieldErrors.password)} pl-10 pr-10`} />
                        <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400">{showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button>
                      </div>
                    </FormField>
                    <FormField label="Confirmar contraseña" error={fieldErrors.confirmPassword}>
                      <div className="relative"><Lock className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-600" /><input required type={showPassword ? "text" : "password"} value={enrollForm.confirmPassword} onChange={set("confirmPassword")} placeholder="Repetí tu contraseña" className={`${inputCls(fieldErrors.confirmPassword)} pl-10`} /></div>
                    </FormField>
                  </div>

                  {enrollForm.company && (
                    <p className="text-[13px] text-gray-600">Workspace: <span className="font-medium text-gray-400">{slugify(enrollForm.company)}.moio.ai</span></p>
                  )}

                  <button type="submit" disabled={submitting} className="group relative flex w-full items-center justify-center gap-2.5 overflow-hidden rounded-xl bg-[#58a6ff] px-6 py-4 text-[15px] font-semibold text-white transition-all hover:shadow-[0_0_40px_rgba(88,166,255,0.25)] disabled:opacity-60 disabled:cursor-not-allowed">
                    {submitting ? <><Loader2 className="h-4 w-4 animate-spin" />Creando tu plataforma...</> : <><Send className="h-4 w-4" />Crear mi cuenta gratuita<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>}
                    <div className="absolute inset-0 bg-gradient-to-r from-[#58a6ff] to-[#3b82f6] opacity-0 transition-opacity group-hover:opacity-100" />
                  </button>
                  <p className="text-center text-[12px] text-gray-700">Al registrarte aceptás nuestros términos de servicio y política de privacidad.</p>
                </form>
              </GradientBorder>
            </motion.div>
          )}
        </motion.div>
      </section>

      {/* ━━━ FAQ ━━━ */}
      <section id="faq" className="mx-auto max-w-3xl px-6 py-32">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-100px" }} variants={stagger} className="text-center">
          <motion.div variants={fadeUp} custom={0}><Badge>FAQ</Badge></motion.div>
          <motion.h2 variants={fadeUp} custom={1} className="mt-5 text-3xl font-bold tracking-tight sm:text-[2.5rem]">Preguntas frecuentes</motion.h2>
        </motion.div>
        <div className="mt-14">
          <GradientBorder>
            <div className="px-8 py-2">
              <FAQItem q="¿Qué incluye el plan gratuito?" a="CRM completo para 5 usuarios durante 12 meses: contactos ilimitados, pipeline de ventas, tickets, actividades y calendario. Sin tarjeta de crédito." />
              <FAQItem q="¿Puedo agregar módulos después?" a="Sí. Chatbot, Flujos y Agent Console se activan y facturan de forma independiente. Cancelá cuando quieras." />
              <FAQItem q="¿Qué canales soporta el chatbot?" a="WhatsApp Business API, Instagram Direct, Facebook Messenger, chat web y Shopify. Todos desde una misma bandeja." />
              <FAQItem q="¿Necesito conocimientos técnicos?" a="No. Los flujos se crean con editor visual y los chatbots se configuran con IA. Sin código." />
              <FAQItem q="¿Se integra con mis herramientas?" a="Shopify, WooCommerce, WhatsApp Business, OpenAI, Mercado Pago, Google APIs, webhooks y API REST completa." />
              <FAQItem q="¿Hay soporte técnico?" a="Todos los planes incluyen soporte por email y chat. Los planes de pago suman soporte prioritario y onboarding." />
            </div>
          </GradientBorder>
        </div>
      </section>

      {/* ━━━ FINAL CTA ━━━ */}
      <section className="mx-auto max-w-7xl px-6 pb-32">
        <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}>
          <div className="relative isolate overflow-hidden rounded-3xl bg-gradient-to-br from-[#58a6ff]/10 via-transparent to-[#2ecc71]/10 p-14 text-center md:p-24">
            <div className="pointer-events-none absolute inset-0 z-0">
              <div className="absolute left-1/2 top-0 h-[300px] w-[400px] -translate-x-1/2 rounded-full bg-[#58a6ff]/10 blur-[100px]" />
            </div>
            <div className="absolute inset-0 rounded-3xl border border-white/[0.06]" />
            <h2 className="relative text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl">
              ¿Listo para transformar<br />tu negocio?
            </h2>
            <p className="relative mx-auto mt-5 max-w-md text-gray-500">
              Unite a las empresas que usan Moio.ai para gestionar, automatizar y crecer — desde el escritorio o el celular.
            </p>
            <a href="#registro" className="relative mt-10 inline-flex items-center gap-2 rounded-xl bg-white px-8 py-4 text-[15px] font-semibold text-[#08080d] transition-all hover:bg-gray-100 hover:shadow-[0_0_40px_rgba(255,255,255,0.1)]">
              Empezar ahora — es gratis <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </motion.div>
      </section>

      {/* ━━━ FOOTER ━━━ */}
      <footer className="border-t border-white/[0.04]">
        <div className="mx-auto max-w-7xl px-6 py-14">
          <div className="grid gap-10 md:grid-cols-4">
            <div>
              <img src={moioLogo} alt="Moio.ai" className="h-6 w-auto" />
              <p className="mt-4 text-[13px] leading-relaxed text-gray-600">
                Plataforma SaaS todo-en-uno para gestionar clientes, automatizar procesos y potenciar tu equipo con IA.
              </p>
            </div>
            {([
              ["Producto", [["#features", "CRM"], ["#features", "Chatbot"], ["#features", "Automatizaciones"], ["#features", "Agent Console"], ["#features", "Data Lab"]]],
              ["Recursos", [["#pricing", "Precios"], ["#faq", "FAQ"], ["/docs", "Documentación API", true], ["#registro", "Contacto"]]],
              ["Legal", [["#", "Términos de servicio"], ["#", "Política de privacidad"]]],
            ] as const).map(([title, links]) => (
              <div key={title}>
                <h4 className="text-[13px] font-semibold text-white">{title}</h4>
                <ul className="mt-4 space-y-2.5 text-[13px] text-gray-600">
                  {links.map(([href, label, isRoute]) => (
                    <li key={label}>{isRoute ? <Link href={href as string} className="transition-colors hover:text-white">{label}</Link> : <a href={href} className="transition-colors hover:text-white">{label}</a>}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-14 flex flex-col items-center justify-between gap-4 border-t border-white/[0.04] pt-8 md:flex-row">
            <p className="text-[12px] text-gray-700">© {new Date().getFullYear()} Moio.ai — Todos los derechos reservados.</p>
            <div className="flex items-center gap-2 text-[12px] text-gray-700">
              <Shield className="h-3.5 w-3.5" /> Datos seguros y encriptados
            </div>
          </div>
        </div>
      </footer>

      </div>
    </div>
  );
}

/* ─── sub-components ─── */

function ShowcaseCard({ icon: Icon, color, title, desc, img, className = "", isMobile = false }: {
  icon: React.ElementType; color: string; title: string; desc: string; img: string; className?: string; isMobile?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <motion.div ref={ref} initial={{ opacity: 0, y: 40 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }} className={className}>
      <GradientBorder className="h-full">
        <div className="group h-full overflow-hidden">
          <div className="p-6 pb-0 md:p-8 md:pb-0">
            <div className="mb-2 flex items-center gap-2.5">
              <div className="rounded-lg p-1.5" style={{ backgroundColor: `${color}10` }}>
                <Icon className="h-4 w-4" style={{ color }} />
              </div>
              <h3 className="text-sm font-semibold text-white">{title}</h3>
            </div>
            <p className="max-w-md text-sm text-gray-500">{desc}</p>
          </div>
          {isMobile ? (
            <div className="mt-5 flex justify-center pb-4">
              <div className="relative overflow-hidden rounded-[1.75rem] border-[3px] border-white/10 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)]">
                <div className="absolute left-1/2 top-0 z-10 h-5 w-24 -translate-x-1/2 rounded-b-xl bg-black" />
                <img src={img} alt={title} className="w-[220px] transition-transform duration-700 ease-out group-hover:scale-[1.02]" />
              </div>
            </div>
          ) : (
            <div className="mt-5 px-4 md:px-6">
              <div className="overflow-hidden rounded-t-xl border border-b-0 border-white/[0.06]">
                <img src={img} alt={title} className="w-full transition-transform duration-700 ease-out group-hover:scale-[1.02]" />
              </div>
            </div>
          )}
        </div>
      </GradientBorder>
    </motion.div>
  );
}

function PricingCard({ title, price, unit, desc, features, highlight, badge, ctaText }: {
  title: string; price: string; unit: string; desc: string; features: string[]; highlight?: boolean; badge?: string; ctaText?: string;
}) {
  return (
    <motion.div variants={fadeUp}>
      <div className={`relative h-full rounded-2xl p-px ${highlight ? "bg-gradient-to-b from-[#58a6ff]/30 via-[#58a6ff]/10 to-transparent" : ""}`}>
        <div className={`relative flex h-full flex-col rounded-2xl border p-7 ${highlight ? "border-[#58a6ff]/20 bg-[#0c0c14]" : "border-white/[0.06] bg-[#0c0c14]"}`}>
          {badge && <span className="absolute -top-3 left-6 rounded-full bg-[#ffba08] px-3 py-1 text-[11px] font-bold text-[#08080d]">{badge}</span>}
          <h3 className="text-base font-semibold text-white">{title}</h3>
          <p className="mt-1.5 text-[13px] text-gray-500">{desc}</p>
          <div className="mt-5 flex items-baseline gap-1">
            <span className="text-4xl font-bold tracking-tight text-white">{price}</span>
            <span className="text-[13px] text-gray-500">{unit}</span>
          </div>
          <ul className="mt-6 flex-1 space-y-2.5">
            {features.map(f => (
              <li key={f} className="flex items-start gap-2.5 text-[13px] text-gray-400">
                <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#2ecc71]" />{f}
              </li>
            ))}
          </ul>
          <a href="#registro" className={`mt-7 flex items-center justify-center gap-2 rounded-xl px-5 py-3 text-[13px] font-semibold transition-all duration-200 ${highlight ? "bg-[#58a6ff] text-white hover:shadow-[0_0_30px_rgba(88,166,255,0.25)]" : "border border-white/[0.08] text-white hover:bg-white/[0.03]"}`}>
            {ctaText || "Comenzar ahora"}<ArrowRight className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </motion.div>
  );
}

function FormField({ label, error, children }: { label: React.ReactNode; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[13px] font-medium text-gray-300">{label}</label>
      {children}
      {error && <p className="mt-1 text-[12px] text-[#ff6b6b]">{error}</p>}
    </div>
  );
}

function PhoneFrame({ img, alt, delay = 0, className = "", featured = false }: {
  img: string; alt: string; delay?: number; className?: string; featured?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-60px" });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 50 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
      className={`relative ${className}`}
    >
      <div className={`relative overflow-hidden rounded-[2rem] border-[3px] ${featured ? "border-white/20 shadow-[0_0_60px_rgba(88,166,255,0.15)]" : "border-white/10 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)]"}`}>
        {/* Status bar notch */}
        <div className="absolute left-1/2 top-0 z-10 h-6 w-28 -translate-x-1/2 rounded-b-2xl bg-black" />
        <div className="relative w-[200px] sm:w-[220px]">
          <img src={img} alt={alt} className="w-full" />
        </div>
      </div>
      <p className={`mt-3 text-center text-[11px] font-medium ${featured ? "text-gray-300" : "text-gray-600"}`}>{alt}</p>
    </motion.div>
  );
}
