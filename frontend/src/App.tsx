import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { TopNavbar } from "./components/TopNavbar";
import { ChatWidget } from "./components/ChatWidget";
import { BackToChatButton } from "./components/BackToChatButton";
import { Footer } from "./components/Footer";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./hooks/useAuth";
import { Landing } from "./routes/Landing";
import { Home } from "./routes/Home";
import { Login } from "./routes/sale/Login";
import { Register } from "./routes/Register";
import { RegisterBusiness } from "./routes/RegisterBusiness";
import { SalePage } from "./routes/sale/SalePage";
import { CustomerChatPage } from "./routes/CustomerChatPage";
import { CategoryDetailPage } from "./routes/sale/CategoryDetailPage";
import { ZoneDetailPage } from "./routes/sale/ZoneDetailPage";
import { CatalogGroupPage } from "./routes/sale/CatalogGroupPage";
import { ProjectOverviewPage } from "./routes/sale/ProjectOverviewPage";
import { NotFound } from "./routes/NotFound";
import { NewsPage } from "./routes/NewsPage";
import { NewsDetailPage } from "./routes/NewsDetailPage";

// Staff-only screens are split into their own chunks: an anonymous visitor or customer never
// downloads the admin console, the live inbox or the news workspace.
function lazyPage<Name extends string>(load: () => Promise<Record<Name, ComponentType>>, name: Name) {
  return lazy(() => load().then((module) => ({ default: module[name] })));
}

const LiveInboxPage = lazyPage(() => import("./routes/sale/LiveInboxPage"), "LiveInboxPage");
const LiveChatPage = lazyPage(() => import("./routes/sale/LiveChatPage"), "LiveChatPage");
const AdminHome = lazyPage(() => import("./routes/admin/AdminHome"), "AdminHome");
const DocumentsTab = lazyPage(() => import("./routes/admin/DocumentsTab"), "DocumentsTab");
const DocumentReviewTab = lazyPage(() => import("./routes/admin/DocumentReviewTab"), "DocumentReviewTab");
const DocumentRelationsTab = lazyPage(() => import("./routes/admin/DocumentRelationsTab"), "DocumentRelationsTab");
const EvalTab = lazyPage(() => import("./routes/admin/EvalTab"), "EvalTab");
const ConflictsTab = lazyPage(() => import("./routes/admin/ConflictsTab"), "ConflictsTab");
const BillingRequestsTab = lazyPage(() => import("./routes/admin/BillingRequestsTab"), "BillingRequestsTab");
const SalesManagementPage = lazyPage(() => import("./routes/admin/SalesManagementPage"), "SalesManagementPage");
const ObservabilityPage = lazyPage(() => import("./routes/admin/ObservabilityPage"), "ObservabilityPage");
const NewsWorkspacePage = lazyPage(() => import("./routes/NewsWorkspacePage"), "NewsWorkspacePage");

const pageFallback = (
  <p className="empty-state" role="status">
    Đang tải…
  </p>
);

/** Admin gets its own dashboard; Sale and Customer see the chat-oriented home page. */
function HomeRoute() {
  const { role } = useAuth();
  return role === "admin" ? <AdminHome /> : <Home />;
}

/** `/chat` is reachable by everyone — anonymous visitors and Customer accounts get the
 * public chat flow (PUBLIC-tier retrieval only, enforced server-side, see
 * backend/routers/customer_chat.py); Sale keeps the existing consultation chat; Admin
 * doesn't consult customers directly, so it redirects home like before. Deliberately a
 * top-level route rather than nested under the authenticated AppShell below, since an
 * anonymous visitor must reach it without ever hitting a login redirect. */
function ChatRoute() {
  const { isAuthenticated, role } = useAuth();
  const { pathname } = useLocation();

  if (isAuthenticated && role === "admin") return <Navigate to="/home" replace />;

  // Two separate pages rather than one page with a toggle: /chat is the AI assistant and
  // /chat/tu-van is the live consultant, matching the two nav dropdown items. Sale keeps
  // its own consultation UI on /chat regardless of the sub-path.
  const isHumanChat = pathname.startsWith("/chat/tu-van");

  return (
    <div className="app-shell">
      <TopNavbar />
      <div className="app-content">
        {role === "sale" ? <SalePage /> : <CustomerChatPage mode={isHumanChat ? "human" : "ai"} />}
      </div>
    </div>
  );
}

/** Shared shell: top nav bar plus content area.
 *
 * Reachable without an account: /inventory/* is public catalogue/pricing browsing (the
 * same information a real showroom shows openly — see backend/routers/projects.py), and the
 * public homepage links straight into it. /home and every admin route stay gated by their
 * own <ProtectedRoute> below; the shell itself no longer blanket-requires login. */
function AppShell() {
  const { role } = useAuth();
  const location = useLocation();
  // LiveChatPage (a claimed live-handoff session) is full-height/no-scroll like /chat's
  // pages, so the Footer/ChatWidget below must stay off it for the same reason those are
  // already off /chat: "adding the Footer would push the height past 100vh". The bare
  // /live-inbox list page is a normal scrolling page and keeps both.
  const isLiveChatPage = /^\/live-inbox\/.+/.test(location.pathname);

  return (
    <div className="app-shell">
      <TopNavbar />
      <div className="app-content">
        <Suspense fallback={pageFallback}>
          <Routes>
          <Route
            path="/home"
            element={
              <ProtectedRoute>
                <HomeRoute />
              </ProtectedRoute>
            }
          />

          {/* Project lookup by product type — reached directly via the TopNavbar dropdown;
              there is no separate /inventory index page anymore (it duplicated the menu).
              Public: same catalogue/pricing an anonymous visitor sees on the homepage. */}
          <Route path="/inventory/:categorySlug" element={<CategoryDetailPage />} />
          {/* One zone (phân khu) per page. Static segments above/below ("group", "project")
              are more specific, so React Router still matches those first. */}
          <Route path="/inventory/:categorySlug/:zoneSlug" element={<ZoneDetailPage />} />
          {/* Group/sub-zone within the multi-project catalog (e.g. "The Metropolitan" = Beverly/London/Paris/Zurich). */}
          <Route path="/inventory/group/:groupSlug" element={<CatalogGroupPage />} />
          {/* Detail page for one real sub-project (The Beverly, The Sapphire...), distinct from
              CategoryDetailPage above, which only shows Vinhomes Ocean Park's overview by product type. */}
          <Route path="/inventory/project/:projectId" element={<ProjectOverviewPage />} />
          {/* Public official-news feed: anonymous, Customer, Sale and Admin share it. */}
          <Route path="/news" element={<NewsPage />} />
          <Route path="/news/:articleId" element={<NewsDetailPage />} />
          <Route
            path="/news-workspace"
            element={
              <ProtectedRoute allowedRole={["sale", "admin"]}>
                <NewsWorkspacePage />
              </ProtectedRoute>
            }
          />

          {/* AI -> Sale live handoff queue — Sale and Admin both work it, no per-region
              assignment (see the plan's scope decisions). */}
          <Route
            path="/live-inbox"
            element={
              <ProtectedRoute allowedRole={["sale", "admin"]}>
                <LiveInboxPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/live-inbox/:sessionId"
            element={
              <ProtectedRoute allowedRole={["sale", "admin"]}>
                <LiveChatPage />
              </ProtectedRoute>
            }
          />

          {/* ADMIN-only area */}
          <Route
            path="/sales"
            element={
              <ProtectedRoute allowedRole="admin">
                <SalesManagementPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/observability"
            element={
              <ProtectedRoute allowedRole="admin">
                <ObservabilityPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/documents"
            element={
              <ProtectedRoute allowedRole="admin">
                <DocumentsTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/document-review"
            element={
              <ProtectedRoute allowedRole="admin">
                <DocumentReviewTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/document-relations"
            element={
              <ProtectedRoute allowedRole="admin">
                <DocumentRelationsTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/eval"
            element={
              <ProtectedRoute allowedRole="admin">
                <EvalTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conflicts"
            element={
              <ProtectedRoute allowedRole="admin">
                <ConflictsTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing-requests"
            element={
              <ProtectedRoute allowedRole="admin">
                <BillingRequestsTab />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </div>

      {/* The marketing footer (contact, resources) means nothing inside the admin console. */}
      {role !== "admin" && !isLiveChatPage && <Footer />}
      {role !== "admin" && !isLiveChatPage && <ChatWidget />}
      {role !== "admin" && !isLiveChatPage && <BackToChatButton />}
    </div>
  );
}

// Single entry point. `/`, `/chat` and `/inventory/*` are public; `/home` and the admin
// pages require login and route after that by role (SALE / ADMIN / CUSTOMER) — each one
// guarded individually inside AppShell/ChatRoute rather than with one blanket wrapper here.
function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      {/* Business sign-up files a subscription request; /register still creates CUSTOMER accounts. */}
      <Route path="/register-business" element={<RegisterBusiness />} />
      <Route path="/chat/*" element={<ChatRoute />} />
      <Route path="*" element={<AppShell />} />
    </Routes>
  );
}

export default App;
