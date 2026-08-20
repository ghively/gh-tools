# GitLab 19.x CE — enumerated API surface

Enumerated from the live instance (GraphQL introspection) plus the version-pinned
v19.x REST resource index. REST base: `/api/v4`. GraphQL: `POST /api/graphql`.

## REST — project-scoped resources

Access requests · Access tokens (project) · Agents (cluster) · Branches ·
Commits · Container registry · Container repository/tag protection rules ·
Custom attributes · Package distributions (Composer, Conan v1/v2, Debian, Go proxy,
Helm, Maven, NPM, NuGet, PyPI, Ruby gems, Terraform modules, generic) · Deploy keys ·
Deploy tokens · Deployments · Discussions · Draft notes · Emoji reactions ·
Environments · Error tracking · Events · Feature flags + user lists · Freeze periods ·
Integrations · Invitations · Issue boards · Issue links · Issues + statistics ·
CI/CD job token scope · Jobs + artifacts · Labels · Members · Merge request approvals
(basic) · Merge requests · Metadata · Model registry · Notes · Notification settings ·
Packages · Pages + domains · Project badges · Project clusters (cert-based, deprecated) ·
Project import/export · Milestones · Snippets · Templates · Wikis · Project-level
variables · Projects · Protected branches · Protected tags · Protected packages/registry ·
Pipeline schedules · Pipeline triggers · Pipelines · Release links · Releases ·
Remote mirrors · Repositories · Repository files · Submodules · Resource label events ·
Runners (project) · Search (incl. blobs/commits/notes/wiki_blobs scopes) · Tags ·
CI lint · Webhooks (project)

**EE-only at project scope (404 on CE):** merge trains, approval rules,
external status checks, protected environments, vulnerabilities/findings/exports,
dependencies.

## REST — group-scoped resources

Access requests/tokens · Custom attributes · Debian distributions · Deploy tokens ·
Discussions · Groups CRUD/transfer · Badges · Issue boards · Labels · Group-level
variables · Milestones · Releases (read) · Invitations · Issues · Members ·
Merge requests · Notes · Notification settings · Packages · Registry repositories ·
Resource label events · Runners · Search · Subgroups/descendants

**EE-only at group scope (404 on CE):** epics + epic issues/links, iterations,
group hooks, group wikis, SSH certificates, LDAP sync, member roles, linked epics.

## REST — instance/admin & standalone resources

Application appearance · Applications (OAuth) · Avatar · Broadcast messages ·
Personal snippets · Custom attributes · Deploy keys (all) · Deploy tokens (all) ·
Events · Instance feature flags (`/features`) · Instance clusters (deprecated) ·
Instance CI/CD variables (`/admin/ci/variables`) · Import (GitHub/Bitbucket) ·
Issues/MRs (scope=all) · Jobs (`/job`) · Keys lookup · License (EE → 404) ·
Markdown render · Namespaces · Notification settings · Pages domains (admin) ·
Personal access tokens · Plan limits · Projects (all) · Repository storage moves
(project/group/snippet) · Runners (`/runners/all`, `/user/runners`) · Search ·
Service data · Settings (`/application/settings`) · Sidekiq metrics + queue admin ·
Statistics · Suggestions · System hooks · To-dos · Topics · Users · Version/Metadata ·
Web commits public key

**EE-only at instance scope (404 on CE):** audit events, Geo nodes, GitLab Duo /
Code Suggestions, compliance/policy settings, Group activity analytics, GLQL(-partial),
member roles.

## Endpoint patterns

The `gitlab_api_search(keyword)` MCP tool returns concrete endpoint templates for
~60 domains. For anything else, GitLab's REST follows predictable patterns:

```
GET    /api/v4/<scope>/:id/<resource>            list
GET    /api/v4/<scope>/:id/<resource>/:rid       get
POST   /api/v4/<scope>/:id/<resource>            create
PUT    /api/v4/<scope>/:id/<resource>/:rid       update
DELETE /api/v4/<scope>/:id/<resource>/:rid       delete
```

where `<scope>` is `projects` / `groups` (id = number or URL-encoded full path)
or nothing for instance resources.

## GraphQL surface (from live introspection)

### GraphQL root queries (160)

```
abuseReport, accessTokenPermissions, addOnPurchases, adminGroups, adminMemberRole
adminMemberRolePermissions, adminMemberRoles, adminProjects, aiCatalogAgentFlowConfig
aiCatalogAvailableFlowsForProject, aiCatalogBuiltInTools, aiCatalogConfiguredItems
aiCatalogCustomAndFoundationalItems, aiCatalogItem, aiCatalogItemConsumer
aiCatalogItemVersions, aiCatalogItems, aiCatalogMcpServer, aiCatalogMcpServers
aiCatalogMcpTools, aiChatAvailableModels, aiChatContextPresets, aiChatIncludedProjects
aiConversationThreads, aiDomainSettings, aiFeatureSettings, aiFoundationalChatAgents
aiMessages, aiModelSelectionNamespaceSettings, aiSelfHostedModels, aiSlashCommands
aiUsageData, auditEventDefinitions, auditEventsInstanceAmazonS3Configurations
auditEventsInstanceStreamingDestinations, blobSearch, boardList, ciApplicationSettings
ciCatalogResource, ciCatalogResources, ciConfig, ciDedicatedHostedRunnerFilters
ciDedicatedHostedRunnerUsage, ciMinutesUsage, ciPipelineStage, ciQueueingHistory, ciVariables
cloudConnectorStatus, complianceFrameworkTemplates, complianceRequirementControls
containerRepository, currentLicense, currentUser, customDashboard, customDashboards
customField, dependency, designManagement, devopsAdoptionEnabledNamespaces
duoDefaultNamespaceCandidates, duoSettings, duoWorkflowEvents, duoWorkflowWorkflows, echo
epicBoardList, featureFlagEnabled, frecentGroups, frecentProjects, geoNode
gitlabCreditsAvailable, gitpodEnabled, googleCloudArtifactRegistryRepositoryArtifact, group
groupSecret, groupSecrets, groupSecretsCount, groupSecretsManager
groupSecretsNeedingRotation, groupSecretsPermissions, groups
instanceExternalAuditEventDestinations, instanceGoogleCloudLoggingConfigurations
instanceSecretsManagerEnrollment, instanceSecurityDashboard, integrationExclusions, issue
issues, iteration, jobs, ldapAdminRoleLinks, licenseHistoryEntries, memberRole
memberRolePermissions, memberRoles, mergeRequest, metadata, milestone, mlExperiment, mlModel
namespace, namespaceSecretsManagerEnrollment, namespaceSecurityProjects, note, openbaoHealth
organization, organizations, package, packageMetadataAdvisories, packageMetadataAdvisory
pipelineExecutionSchedulePolicyTestRun, project, projectComplianceViolation, projectSecret
projectSecrets, projectSecretsCount, projectSecretsManager, projectSecretsNeedingRotation
projectSecretsPermissions, projects, queryComplexity, runner, runnerPlatforms, runnerSetup
runnerUsage, runnerUsageByProject, runners, secretPermissions, securityConfiguration
securityPoliciesSyncStatus, securityScanProfile, selfManagedAddOnEligibleUsers
selfManagedUsersQueuedForRolePromotion, snippets, standardRole, standardRoles
subscriptionFutureEntries, subscriptionUsage, syntheticNote, timelogs, todo, topics
trialUsage, usageTrendsMeasurements, user, users, virtualRegistriesContainerRegistry
virtualRegistriesContainerUpstream, virtualRegistriesPackagesMavenRegistry
virtualRegistriesPackagesMavenUpstream, vulnerabilities, vulnerabilitiesCountByDay
vulnerability, wikiPage, workItem, workItemAllowedStatuses
workItemDescriptionTemplateContent, workItemTypeIconDefinitions, workItemsByReference
workspace, workspaces
```

### GraphQL mutations (622)

```
achievementsAward, achievementsCreate, achievementsDelete, achievementsRevoke
achievementsUpdate, addProjectToSecurityDashboard, adminRolesLdapSync
adminSidekiqQueuesDeleteJobs, aiAction, aiAgentCreate, aiCatalogAgentCreate
aiCatalogAgentDelete, aiCatalogAgentUpdate, aiCatalogFlowCreate, aiCatalogFlowDelete
aiCatalogFlowUpdate, aiCatalogItemConsumerCreate, aiCatalogItemConsumerDelete
aiCatalogItemConsumerUpdate, aiCatalogItemReport, aiCatalogItemStar, aiCatalogMcpServerCreate
aiCatalogMcpServerUpdate, aiCatalogThirdPartyFlowCreate, aiCatalogThirdPartyFlowDelete
aiCatalogThirdPartyFlowUpdate, aiDomainSettingsInstanceUpdate
aiDomainSettingsNamespaceUpdate, aiDuoWorkflowCreate, aiFeatureSettingUpdate
aiFlowTriggerCreate, aiFlowTriggerDelete, aiFlowTriggerUpdate
aiModelSelectionNamespaceUpdate, aiSelfHostedModelConnectionCheck, aiSelfHostedModelCreate
aiSelfHostedModelDelete, aiSelfHostedModelUpdate, alertSetAssignees, alertTodoCreate
approvalProjectRuleDelete, approvalProjectRuleUpdate, approveDeployment, artifactDestroy
ascpComponentCreate, ascpScanCreate, ascpSecurityContextCreate
auditEventsAmazonS3ConfigurationCreate, auditEventsAmazonS3ConfigurationDelete
auditEventsAmazonS3ConfigurationUpdate, auditEventsGroupDestinationEventsAdd
auditEventsGroupDestinationEventsDelete, auditEventsGroupDestinationNamespaceFilterCreate
auditEventsGroupDestinationNamespaceFilterDelete
auditEventsInstanceAmazonS3ConfigurationCreate
auditEventsInstanceAmazonS3ConfigurationDelete
auditEventsInstanceAmazonS3ConfigurationUpdate, auditEventsInstanceDestinationEventsAdd
auditEventsInstanceDestinationEventsDelete
auditEventsInstanceDestinationNamespaceFilterCreate
auditEventsInstanceDestinationNamespaceFilterDelete, auditEventsStreamingDestinationEventsAdd
auditEventsStreamingDestinationEventsRemove, auditEventsStreamingDestinationInstanceEventsAdd
auditEventsStreamingDestinationInstanceEventsRemove, auditEventsStreamingHeadersCreate
auditEventsStreamingHeadersDestroy, auditEventsStreamingHeadersUpdate
auditEventsStreamingHttpNamespaceFiltersAdd, auditEventsStreamingHttpNamespaceFiltersDelete
auditEventsStreamingInstanceHeadersCreate, auditEventsStreamingInstanceHeadersDestroy
auditEventsStreamingInstanceHeadersUpdate, awardEmojiAdd, awardEmojiRemove, awardEmojiToggle
boardEpicCreate, boardListCreate, boardListUpdateLimitMetrics, branchDelete
branchRuleApprovalProjectRuleCreate, branchRuleCreate, branchRuleDelete
branchRuleExternalStatusCheckCreate, branchRuleExternalStatusCheckDestroy
branchRuleExternalStatusCheckUpdate, branchRuleSquashOptionDelete
branchRuleSquashOptionUpdate, branchRuleUpdate, bulkDestroyJobArtifacts
bulkEnableDevopsAdoptionNamespaces, bulkRunnerDelete, bulkSetVulnerabilityFindingsDueDates
bulkUpdateSecurityAttributes, catalogResourcesCreate, catalogResourcesDestroy
ciJobTokenScopeAddGroupOrProject, ciJobTokenScopeAddProject, ciJobTokenScopeRemoveGroup
ciJobTokenScopeRemoveProject, ciJobTokenScopeUpdatePolicies, ciLint, clusterAgentDelete
clusterAgentTokenCreate, clusterAgentTokenRevoke, clusterAgentUrlConfigurationCreate
clusterAgentUrlConfigurationDelete, commitCreate, configureContainerScanning
configureDependencyScanning, configureSast, configureSastIac, configureSecretDetection
containerCacheEntryDelete, containerUpstreamCacheDelete, containerUpstreamCreate
containerUpstreamDelete, containerUpstreamTest, containerUpstreamUpdate
containerVirtualRegistryCacheDelete, containerVirtualRegistryCreate
containerVirtualRegistryDelete, containerVirtualRegistryUpdate
containerVirtualRegistryUpstreamCreate, containerVirtualRegistryUpstreamDelete
containerVirtualRegistryUpstreamUpdate, corpusCreate, createAlertIssue, createAnnotation
createBoard, createBranch, createClusterAgent, createComplianceFramework
createComplianceFrameworkFromTemplate, createComplianceRequirement
createComplianceRequirementsControl, createContainerProtectionRepositoryRule
createContainerProtectionTagRule, createCustomDashboard, createCustomEmoji, createDiffNote
createDiscussion, createEpic, createImageDiffNote, createIssue, createIteration
createLatestDiffNote, createNote, createPackagesProtectionRule, createRequirement
createSnippet, createTestCase, customFieldArchive, customFieldCreate, customFieldUnarchive
customFieldUpdate, customerRelationsContactCreate, customerRelationsContactUpdate
customerRelationsOrganizationCreate, customerRelationsOrganizationUpdate
dastOnDemandScanCreate, dastProfileCreate, dastProfileDelete, dastProfileRun
dastProfileUpdate, dastScannerProfileCreate, dastScannerProfileDelete
dastScannerProfileUpdate, dastSiteProfileCreate, dastSiteProfileDelete, dastSiteProfileUpdate
dastSiteTokenCreate, dastSiteValidationCreate, dastSiteValidationRevoke, deleteAnnotation
deleteContainerProtectionRepositoryRule, deleteContainerProtectionTagRule
deleteConversationThread, deleteCustomDashboard, deleteDuoWorkflowsWorkflow
deleteGroupCustomAttribute, deletePackagesProtectionRule, deletePagesDeployment
deleteProjectCustomAttribute, deleteUserCustomAttribute, designManagementDelete
designManagementMove, designManagementUpdate, designManagementUpload, destroyBoard
destroyBoardList, destroyComplianceFramework, destroyComplianceRequirement
destroyComplianceRequirementsControl, destroyContainerRepository
destroyContainerRepositoryTags, destroyCustomEmoji, destroyEpicBoard, destroyNote
destroyPackage, destroyPackageFile, destroyPackageFiles, destroyPackages, destroySnippet
devfileValidate, disableDevopsAdoptionNamespace, discussionToggleResolve
dismissPolicyViolations, duoSettingsUpdate, duoUserFeedback, echoCreate
enableDevopsAdoptionNamespace, environmentCreate, environmentDelete, environmentStop
environmentUpdate, environmentsCanaryIngressUpdate, epicAddIssue, epicBoardCreate
epicBoardListCreate, epicBoardListDestroy, epicBoardUpdate, epicMoveList, epicSetSubscription
epicTreeReorder, escalationPolicyCreate, escalationPolicyDestroy, escalationPolicyUpdate
exportRequirements, externalAuditEventDestinationCreate, externalAuditEventDestinationDestroy
externalAuditEventDestinationUpdate, geoRegistriesBulkUpdate, geoRegistriesUpdate
gitlabSubscriptionActivate, googleCloudLoggingConfigurationCreate
googleCloudLoggingConfigurationDestroy, googleCloudLoggingConfigurationUpdate
groupAuditEventStreamingDestinationsCreate, groupAuditEventStreamingDestinationsDelete
groupAuditEventStreamingDestinationsUpdate, groupMemberBulkUpdate, groupMembersExport
groupSavedReplyCreate, groupSavedReplyDestroy, groupSavedReplyUpdate, groupSecretCreate
groupSecretDelete, groupSecretUpdate, groupSecretsManagerDeprovision
groupSecretsManagerInitialize, groupSecretsPermissionDelete, groupSecretsPermissionUpdate
groupUpdate, httpIntegrationCreate, httpIntegrationDestroy, httpIntegrationResetToken
httpIntegrationUpdate, importSourceUserCancelReassignment
importSourceUserKeepAllAsPlaceholder, importSourceUserKeepAsPlaceholder
importSourceUserReassign, importSourceUserResendNotification
importSourceUserRetryFailedReassignment, importSourceUserUndoKeepAsPlaceholder
instanceAuditEventStreamingDestinationsCreate, instanceAuditEventStreamingDestinationsDelete
instanceAuditEventStreamingDestinationsUpdate, instanceExternalAuditEventDestinationCreate
instanceExternalAuditEventDestinationDestroy, instanceExternalAuditEventDestinationUpdate
instanceGoogleCloudLoggingConfigurationCreate, instanceGoogleCloudLoggingConfigurationDestroy
instanceGoogleCloudLoggingConfigurationUpdate, instanceSecretsManagerEnroll
instanceSecretsManagerUnenroll, integrationExclusionCreate, integrationExclusionDelete
issuableResourceLinkCreate, issuableResourceLinkDestroy, issueLinkAlerts, issueMove
issueMoveList, issueSetAssignees, issueSetConfidential, issueSetCrmContacts, issueSetDueDate
issueSetEpic, issueSetEscalationPolicy, issueSetEscalationStatus, issueSetIteration
issueSetLocked, issueSetSeverity, issueSetSubscription, issueSetWeight, issueUnlinkAlert
iterationCadenceCreate, iterationCadenceDestroy, iterationCadenceUpdate, iterationCreate
iterationDelete, jiraImportStart, jiraImportUsers, jobArtifactsDestroy, jobCancel, jobPlay
jobRetry, jobUnschedule, labelCreate, labelUpdate, ldapAdminRoleLinkCreate
ldapAdminRoleLinkDestroy, lifecycleAttachWorkItemType, lifecycleCreate, lifecycleDelete
lifecycleUpdate, linkProjectComplianceViolationIssue, markAsSpamSnippet
mavenCacheEntryDelete, mavenUpstreamCacheDelete, mavenUpstreamCreate, mavenUpstreamDelete
mavenUpstreamUpdate, mavenVirtualRegistryCacheDelete, mavenVirtualRegistryCreate
mavenVirtualRegistryDelete, mavenVirtualRegistryUpdate, mavenVirtualRegistryUpstreamDelete
mavenVirtualRegistryUpstreamUpdate, memberRoleAdminCreate, memberRoleAdminDelete
memberRoleAdminUpdate, memberRoleCreate, memberRoleDelete, memberRoleToUserAssign
memberRoleUpdate, mergeRequestAccept, mergeRequestBypassSecurityPolicy, mergeRequestCreate
mergeRequestDestroyRequestedChanges, mergeRequestRequestChanges, mergeRequestReviewerRereview
mergeRequestSetAssignees, mergeRequestSetBlockingMergeRequests, mergeRequestSetDraft
mergeRequestSetLabels, mergeRequestSetLocked, mergeRequestSetMilestone
mergeRequestSetReviewers, mergeRequestSetSubscription, mergeRequestUpdate
mergeRequestUpdateApprovalRule, mergeTrainsDeleteCar, mlModelCreate, mlModelDelete
mlModelDestroy, mlModelEdit, mlModelVersionCreate, mlModelVersionDelete, mlModelVersionEdit
namespaceBanDestroy, namespaceCiCdSettingsUpdate
namespaceCreateRemoteDevelopmentClusterAgentMapping
namespaceDeleteRemoteDevelopmentClusterAgentMapping, namespaceSecretsManagerEnroll
namespaceSecretsManagerUnenroll, namespaceSettingsUpdate
namespacesRegenerateNewWorkItemEmailAddress, noteConvertToThread, oncallRotationCreate
oncallRotationDestroy, oncallRotationUpdate, oncallScheduleCreate, oncallScheduleDestroy
oncallScheduleUpdate, orbitUpdate, organizationCreate, organizationCreateClusterAgentMapping
organizationDeleteClusterAgentMapping, organizationUpdate, organizationUserUpdate
pagesMarkOnboardingComplete, personalAccessTokenCreate, personalAccessTokenRevoke
personalAccessTokenRotate, pipelineCancel, pipelineCreate, pipelineDestroy
pipelineExecutionSchedulePolicyTestRun, pipelineRetry, pipelineScheduleCreate
pipelineScheduleDelete, pipelineSchedulePlay, pipelineScheduleTakeOwnership
pipelineScheduleUpdate, pipelineTriggerCreate, pipelineTriggerDelete, pipelineTriggerUpdate
processUserBillablePromotionRequest, productAnalyticsProjectSettingsUpdate
projectBlobsRemove, projectCiCdSettingsUpdate, projectCustomAttributeSet
projectInitializeProductAnalytics, projectMemberBulkUpdate, projectSavedReplyCreate
projectSavedReplyDestroy, projectSavedReplyUpdate, projectSecretCreate, projectSecretDelete
projectSecretUpdate, projectSecretsManagerDeprovision, projectSecretsManagerInitialize
projectSecretsPermissionDelete, projectSecretsPermissionUpdate
projectSecurityExclusionCreate, projectSecurityExclusionDelete
projectSecurityExclusionUpdate, projectSetComplianceFramework
projectSetContinuousVulnerabilityScanning, projectSetLocked, projectSettingsUpdate
projectSubscriptionCreate, projectSubscriptionDelete, projectSyncFork
projectTargetBranchRuleCreate, projectTargetBranchRuleDestroy, projectTextReplace
projectUpdateComplianceFrameworks, prometheusIntegrationCreate
prometheusIntegrationResetToken, prometheusIntegrationUpdate, promoteToEpic
refreshFindingTokenStatus, refreshSecurityFindingTokenStatus, refreshStandardsAdherenceChecks
refreshVulnerabilityFindingTokenStatus, releaseAssetLinkCreate, releaseAssetLinkDelete
releaseAssetLinkUpdate, releaseCreate, releaseDelete, releaseUpdate
removeProjectFromSecurityDashboard, repositionImageDiffNote, restorePagesDeployment
resyncSecurityPolicies, runnerAssignToProject, runnerBulkPause, runnerCacheClear
runnerCreate, runnerDelete, runnerUnassignFromProject, runnerUpdate, runnersExportUsage
runnersRegistrationTokenReset, safeDisablePipelineVariables, savedReplyCreate
savedReplyDestroy, savedReplyUpdate, scanExecutionPolicyCommit, secretPermissionDelete
secretPermissionUpdate, securityAttributeCreate, securityAttributeDestroy
securityAttributeProjectUpdate, securityAttributeUpdate, securityCategoryCreate
securityCategoryDestroy, securityCategoryUpdate, securityFindingCreateIssue
securityFindingCreateMergeRequest, securityFindingCreateVulnerability, securityFindingDismiss
securityFindingExternalIssueLinkCreate, securityFindingJiraIssueFormUrlCreate
securityFindingRevertToDetected, securityFindingSeverityOverride, securityPolicyProjectAssign
securityPolicyProjectCreate, securityPolicyProjectCreateAsync, securityPolicyProjectUnassign
securityRefsTrack, securityRefsUntrack, securityScanProfileAttach, securityScanProfileDetach
securityTrainingUpdate, setContainerScanningForRegistry, setCvsForContainerScanning
setCvsForDependencyScanning, setGroupCustomAttribute, setGroupSecretPushProtection
setGroupValidityChecks, setLicenseConfigurationSource, setPagesForceHttps
setPagesUseUniqueDomain, setPreReceiveSecretDetection, setSecretPushProtection
setValidityChecks, starProject, tagCreate, tagDelete, terraformStateDelete
terraformStateLock, terraformStateUnlock, timelineEventCreate, timelineEventDestroy
timelineEventPromoteFromNote, timelineEventTagCreate, timelineEventUpdate, timelogCreate
timelogDelete, todoCreate, todoDeleteAllDone, todoDeleteMany, todoMarkDone, todoResolveMany
todoRestore, todoRestoreMany, todoSnooze, todoSnoozeMany, todoUnSnooze, todoUnsnoozeMany
todosMarkAllDone, unlinkProjectComplianceViolationIssue, updateAlertStatus, updateBoard
updateBoardEpicUserPreferences, updateBoardList, updateComplianceFramework
updateComplianceRequirement, updateComplianceRequirementsControl
updateContainerExpirationPolicy, updateContainerProtectionRepositoryRule
updateContainerProtectionTagRule, updateCustomDashboard
updateDependencyProxyImageTtlGroupPolicy, updateDependencyProxyPackagesSettings
updateDependencyProxySettings, updateDuoWorkflowToolCallApprovals, updateEpic
updateEpicBoardList, updateImageDiffNote, updateIssue, updateIteration
updateNamespacePackageSettings, updateNote, updatePackagesCleanupPolicy
updatePackagesProtectionRule, updateProjectComplianceViolation, updateRequirement
updateSnippet, updateTerraformStateProtectionRule, updateVirtualRegistriesSetting
uploadCreate, uploadDelete, upsertFlatUserCap, upsertUserBudgetCapOverrides
userAchievementPrioritiesUpdate, userAchievementsDelete, userAchievementsUpdate
userAddOnAssignmentBulkCreate, userAddOnAssignmentBulkRemove, userAddOnAssignmentCreate
userAddOnAssignmentRemove, userCalloutCreate, userCustomAttributeSet, userGroupCalloutCreate
userPreferencesUpdate, userSetNamespaceCommitEmail, valueStreamCreate, valueStreamDestroy
valueStreamUpdate, verifiedNamespaceCreate, virtualRegistriesCleanupPolicyUpsert
vulnerabilitiesArchive, vulnerabilitiesCreateIssue, vulnerabilitiesDismiss
vulnerabilitiesRemoveAllFromProject, vulnerabilitiesSeverityOverride, vulnerabilityConfirm
vulnerabilityCreate, vulnerabilityDismiss, vulnerabilityDismissFalsePositiveFlag
vulnerabilityExternalIssueLinkCreate, vulnerabilityExternalIssueLinkDestroy
vulnerabilityIssueLinkCreate, vulnerabilityLinkMergeRequest, vulnerabilityResolve
vulnerabilityRevertToDetected, vulnerabilityUnlinkMergeRequest, wikiPageSubscribe
workItemAddClosingMergeRequest, workItemAddLinkedItems, workItemAvailabilityToggle
workItemBulkMove, workItemBulkUpdate, workItemConvert, workItemCreate, workItemCreateFromTask
workItemDelete, workItemExport, workItemHierarchyAddChildrenItems, workItemRemoveLinkedItems
workItemSavedViewCreate, workItemSavedViewDelete, workItemSavedViewReorder
workItemSavedViewSubscribe, workItemSavedViewUnsubscribe, workItemSavedViewUpdate
workItemSettingsUpdate, workItemSubscribe, workItemTypeCreate, workItemTypeUpdate
workItemUpdate, workItemUserPreferenceUpdate, workItemsCsvExport, workItemsCsvImport
workItemsHierarchyReorder, workItemsReorder, workspaceCreate, workspaceUpdate
```

Note: this list comes from introspection, which OVER-REPORTS on CE — EE/Duo fields
(duoSettings, aiChatAvailableModels, vulnerabilities, epics, iterations, ...) appear
here but are rejected at runtime with "Field '...' doesn't exist". Verified-working
free-tier fields include: workItems, alertManagementAlerts, ciCatalogResources,
achievements, dependencyProxySetting, mlModels/mlExperiments. Introspect argument
details with a targeted __type(name: "...") query via gitlab_graphql.
