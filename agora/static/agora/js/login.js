const { useEffect, useState } = React;

function readJsonScriptContent(id) {
    const element = document.getElementById(id);
    return element ? JSON.parse(element.textContent) : '';
}

function LoginPage() {
    const [username, setUsername] = useState(readJsonScriptContent('login-initial-username'));
    const [password, setPassword] = useState('');
    const [errorMessage] = useState(readJsonScriptContent('login-error-message'));
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        const frame = window.requestAnimationFrame(() => setLoaded(true));
        return () => window.cancelAnimationFrame(frame);
    }, []);

    return (
        <div className="login-shell">
            <section className="login-hero">
                <div className="brand">
                    <span className="brand-mark"></span>
                    <span>Ágora Learning Hub</span>
                </div>

                <div className="hero-copy" style={{ opacity: loaded ? 1 : 0, transform: loaded ? 'translateY(0)' : 'translateY(10px)', transition: 'opacity 320ms ease, transform 320ms ease' }}>
                    <h1>Aprender, ensinar e acompanhar tudo em um só lugar.</h1>
                    <p>
                        Entre na plataforma para acessar cursos, atividades, entregas e o progresso acadêmico da sua jornada no Ágora.
                    </p>
                </div>

                <div className="hero-note">
                    <span>Painel único para estudantes e professores</span>
                </div>
            </section>

            <section className="login-panel-wrap">
                <div className="login-panel">
                    <h2>Entrar</h2>
                    <p>Use seu usuário e senha para acessar o ambiente virtual de aprendizagem.</p>

                    {errorMessage && <div className="login-error">{errorMessage}</div>}

                    <form method="post">
                        <input type="hidden" name="csrfmiddlewaretoken" value={readJsonScriptContent('csrf-token')} />

                        <div className="field">
                            <label htmlFor="username">Usuário</label>
                            <input
                                id="username"
                                name="username"
                                type="text"
                                autoComplete="username"
                                value={username}
                                onChange={(event) => setUsername(event.target.value)}
                                placeholder="Digite seu usuário"
                                required
                            />
                        </div>

                        <div className="field">
                            <label htmlFor="password">Senha</label>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                autoComplete="current-password"
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                placeholder="Digite sua senha"
                                required
                            />
                        </div>

                        <div className="login-actions">
                            <button className="login-button" type="submit">Acessar agora</button>
                            <div className="login-hint">Em breve: cadastro, recuperacao de senha e acesso por perfil.</div>
                        </div>
                    </form>
                </div>
            </section>
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById('login-root'));
root.render(<LoginPage />);