<#-- Gabarit commun des pages de connexion Synapse (écran 1). -->
<#-- Jetons et logo montés depuis design/ et web/public/ (voir infra/docker-compose.yml). -->
<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false displayHeader=true otherArgs...>
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>Connexion · Synapse</title>
  <link rel="icon" href="${url.resourcesPath}/brand/logo-light.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&family=Sora:wght@500;600&display=swap">
  <link rel="stylesheet" href="${url.resourcesPath}/design/tokens.css">
  <link rel="stylesheet" href="${url.resourcesPath}/css/synapse.css">
</head>
<body class="${bodyClass}">
<main class="sy-page">
  <div class="sy-column">
    <header class="sy-header">
      <img src="${url.resourcesPath}/brand/logo-light.png" alt="" width="72" height="72">
      <h1>Synapse</h1>
      <p class="sy-tagline">Ton équipe logicielle IA. Elle propose, tu valides.</p>
    </header>

    <div class="sy-card">
      <#if displayHeader>
        <h2 class="sy-card-title"><#nested "header"></h2>
      </#if>

      <#if auth?has_content && auth.showUsername() && !auth.showResetCredentials()>
        <p class="sy-attempted">
          ${auth.attemptedUsername}
          <a href="${url.loginRestartFlowUrl}">Changer de compte</a>
        </p>
      </#if>

      <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
        <div class="sy-alert sy-alert-${message.type}" role="alert">${kcSanitize(message.summary)?no_esc}</div>
      </#if>

      <#nested "form">
      <#nested "socialProviders">

      <#if displayInfo>
        <div class="sy-info"><#nested "info"></div>
      </#if>
    </div>

    <p class="sy-footer">Pas encore de compte ? Demande une invitation à l’administrateur de ton espace.</p>
  </div>
</main>
</body>
</html>
</#macro>
