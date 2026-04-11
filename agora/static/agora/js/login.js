const { useEffect, useState } = React;

function readJsonScriptContent(id) {
    const element = document.getElementById(id);
    return element ? JSON.parse(element.textContent) : '';
}

function LoginPage() {
    const [activeForm, setActiveForm] = useState(readJsonScriptContent('login-active-form') || 'login');
    const [username, setUsername] = useState(readJsonScriptContent('login-initial-username'));
    const [password, setPassword] = useState('');
    const [registerUsername, setRegisterUsername] = useState(readJsonScriptContent('login-initial-register-username'));
    const [registerEmail, setRegisterEmail] = useState(readJsonScriptContent('login-initial-register-email'));
    const [registerPassword, setRegisterPassword] = useState('');
    const [registerPasswordConfirm, setRegisterPasswordConfirm] = useState('');
    const [errorMessage, setErrorMessage] = useState(readJsonScriptContent('login-error-message'));
    const [loaded, setLoaded] = useState(false);
    const csrfToken = readJsonScriptContent('csrf-token');

    useEffect(() => {
        const frame = window.requestAnimationFrame(() => setLoaded(true));
        return () => window.cancelAnimationFrame(frame);
    }, []);

    function switchForm(nextForm) {
        setActiveForm(nextForm);
        setErrorMessage('');
    }

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
                    <div className="login-tabs" role="tablist" aria-label="Autenticacao">
                        <button
                            className={`login-tab ${activeForm === 'login' ? 'active' : ''}`}
                            type="button"
                            onClick={() => switchForm('login')}
                        >
                            Entrar
                        </button>
                        <button
                            className={`login-tab ${activeForm === 'register' ? 'active' : ''}`}
                            type="button"
                            onClick={() => switchForm('register')}
                        >
                            Criar conta
                        </button>
                    </div>

                    <h2>{activeForm === 'login' ? 'Entrar' : 'Cadastro rápido'}</h2>
                    <p>
                        {activeForm === 'login'
                            ? 'Use seu usuário ou matrícula e senha para acessar o ambiente virtual de aprendizagem.'
                            : 'Crie sua conta para gerar automaticamente uma matrícula de aluno no Ágora.'}
                    </p>

                    {errorMessage && <div className="login-error">{errorMessage}</div>}

                    {activeForm === 'login' ? (
                        <form method="post">
                            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                            <input type="hidden" name="action" value="login" />

                            <div className="field">
                                <label htmlFor="username">Usuário ou matrícula</label>
                                <input
                                    id="username"
                                    name="username"
                                    type="text"
                                    autoComplete="username"
                                    value={username}
                                    onChange={(event) => setUsername(event.target.value)}
                                    placeholder="Digite seu usuário ou matrícula"
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
                                <div className="login-hint">Se ainda nao tiver conta, use a aba Criar conta.</div>
                            </div>
                        </form>
                    ) : (
                        <form method="post">
                            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                            <input type="hidden" name="action" value="register" />

                            <div className="field">
                                <label htmlFor="register_username">Usuário</label>
                                <input
                                    id="register_username"
                                    name="register_username"
                                    type="text"
                                    autoComplete="username"
                                    value={registerUsername}
                                    onChange={(event) => setRegisterUsername(event.target.value)}
                                    placeholder="Escolha um nome de usuário"
                                    required
                                />
                            </div>

                            <div className="field">
                                <label htmlFor="register_email">Email</label>
                                <input
                                    id="register_email"
                                    name="register_email"
                                    type="email"
                                    autoComplete="email"
                                    value={registerEmail}
                                    onChange={(event) => setRegisterEmail(event.target.value)}
                                    placeholder="voce@exemplo.com"
                                />
                            </div>

                            <div className="field">
                                <label htmlFor="register_password">Senha</label>
                                <input
                                    id="register_password"
                                    name="register_password"
                                    type="password"
                                    autoComplete="new-password"
                                    value={registerPassword}
                                    onChange={(event) => setRegisterPassword(event.target.value)}
                                    placeholder="Crie uma senha"
                                    required
                                />
                            </div>

                            <div className="field">
                                <label htmlFor="register_password_confirm">Confirmar senha</label>
                                <input
                                    id="register_password_confirm"
                                    name="register_password_confirm"
                                    type="password"
                                    autoComplete="new-password"
                                    value={registerPasswordConfirm}
                                    onChange={(event) => setRegisterPasswordConfirm(event.target.value)}
                                    placeholder="Repita a senha"
                                    required
                                />
                            </div>

                            <div className="login-actions">
                                <button className="login-button" type="submit">Criar conta</button>
                                <div className="login-hint">O cadastro cria um aluno, gera a matrícula automaticamente e faz login ao concluir.</div>
                            </div>
                        </form>
                    )}
                </div>
            </section>
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById('login-root'));
root.render(<LoginPage />);
