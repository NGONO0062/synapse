<#-- Écran 1 · Connexion — markup repris de docs/maquettes-html/01-Login.html. -->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayHeader=false displayMessage=!messagesPerField.existsError('username','password'); section>
  <#if section = "form">
    <#-- SSO : un bouton par fournisseur d'identité d'entreprise configuré dans le royaume. -->
    <#if realm.password && social.providers?? && social.providers?has_content>
      <#list social.providers as p>
        <a class="sy-btn sy-btn-sso" href="${p.loginUrl}">
          <svg aria-hidden="true" width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="2.5" y="3.5" width="13" height="11" rx="2"></rect><path d="M2.5 5l6.5 5 6.5-5"></path></svg>
          Continuer avec le compte de l’entreprise (${p.displayName!'SSO'})
        </a>
      </#list>
      <div class="sy-divider"><span aria-hidden="true"></span>ou<span aria-hidden="true"></span></div>
    </#if>

    <#if realm.password>
      <form id="kc-form-login" class="sy-form" action="${url.loginAction}" method="post" onsubmit="login.disabled = true; return true;">
        <div class="sy-field">
          <label for="username">E-mail</label>
          <input id="username" name="username" type="text" value="${(login.username!'')}"
                 placeholder="nom@entreprise.com" autocomplete="username" autofocus
                 <#if messagesPerField.existsError('username','password')>aria-invalid="true" aria-describedby="input-error"</#if>>
        </div>

        <div class="sy-field">
          <div class="sy-label-row">
            <label for="password">Mot de passe</label>
            <#if realm.resetPasswordAllowed>
              <a href="${url.loginResetCredentialsUrl}">Mot de passe oublié ?</a>
            </#if>
          </div>
          <input id="password" name="password" type="password" autocomplete="current-password"
                 <#if messagesPerField.existsError('username','password')>aria-invalid="true" aria-describedby="input-error"</#if>>
        </div>

        <#if messagesPerField.existsError('username','password')>
          <p id="input-error" class="sy-alert sy-alert-error" role="alert">
            ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
          </p>
        </#if>

        <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>>
        <button class="sy-btn sy-btn-primary" name="login" id="kc-login" type="submit">Se connecter</button>
      </form>
    </#if>
  </#if>
</@layout.registrationLayout>
