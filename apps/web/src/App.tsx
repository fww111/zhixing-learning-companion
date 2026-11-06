import { createRoot } from "react-dom/client";
import { AppRouter } from "./router/AppRouter";
import "./styles/tokens.css";
import "./styles/app.css";

createRoot(document.getElementById("root")!).render(<AppRouter />);
