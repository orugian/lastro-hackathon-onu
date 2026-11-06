import { useEffect, useState } from "react";
import { AnalyzeModal } from "./AnalyzeModal";
import { DossierPage } from "./DossierPage";
import { Reliability } from "./Reliability";
import { Triage } from "./Triage";
import { ExperimentalSeal, Icon } from "./ui";
import "./App.css";

function useRoute() {
  const [hash, setHash] = useState(() => location.hash || "#/");
  useEffect(() => {
    const on = () => {
      setHash(location.hash || "#/");
      window.scrollTo(0, 0);
    };
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return hash;
}

const LAST = "lastro:last-case";

export default function App() {
  const route = useRoute();
  const [modal, setModal] = useState<string | null>(null);
  const caseMatch = route.match(/^#\/caso\/(.+)$/);
  const autex = caseMatch ? decodeURIComponent(caseMatch[1]) : null;
  const page = autex ? "caso" : route.startsWith("#/confiabilidade") ? "conf" : "triagem";
  const [last, setLast] = useState(() => sessionStorage.getItem(LAST));
  useEffect(() => {
    if (autex) {
      sessionStorage.setItem(LAST, autex);
      setLast(autex);
    }
  }, [autex]);
  useEffect(() => {
    document.title = autex ? `${autex} · Lastro` : page === "conf" ? "Confiabilidade · Lastro" : "Lastro · Triagem";
  }, [autex, page]);

  return (
    <div className="app">
      <header className="top">
        <a className="brand" href="#/">
          <Icon name="logo" size={26} />
          <span className="wordmark">Lastro</span>
        </a>
        <span className="tagline">O volume declarado tem lastro na floresta?</span>
        <nav aria-label="Principal">
          <a className={page === "triagem" ? "on" : ""} href="#/">
            Triagem
          </a>
          {last || autex ? (
            <a className={page === "caso" ? "on" : ""} href={`#/caso/${encodeURIComponent(autex ?? last ?? "")}`}>
              Dossiê
            </a>
          ) : (
            <span className="nav-off" title="Escolha uma autorização na triagem">
              Dossiê
            </span>
          )}
          <a className={page === "conf" ? "on" : ""} href="#/confiabilidade">
            Confiabilidade
          </a>
        </nav>
        <div className="top-right">
          <ExperimentalSeal />
          <button type="button" className="primary" onClick={() => setModal("")}>
            Analisar autorização
          </button>
        </div>
      </header>
      {page === "caso" && autex ? <DossierPage key={autex} autex={autex} openAnalyze={(a) => setModal(a)} /> : page === "conf" ? <Reliability /> : <Triage />}
      {modal !== null && <AnalyzeModal initial={modal} close={() => setModal(null)} />}
    </div>
  );
}
