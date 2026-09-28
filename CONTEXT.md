# Hill 175 Competition Domain Glossary

## Terms

### School Identity
The immutable Entra tenant/object pair representing one eligible Hill person. In Microsoft mode it controls entry limits, team membership and permissions across linked game accounts. Eligibility also requires the configured app role. Voting and moderation extensions remain separate work.

### Minecraft Nickname
The game account's current protocol name, used for account labels and command targeting. A name is not proof of identity. Microsoft mode uses verified Java UUIDs or Floodgate XUIDs for durable game links.

### School Display Name
The approved name from the validated Microsoft `name` claim, displayed as plain text in server interfaces. It is distinct from the Minecraft nickname. Anonymous voting/name suppression is not yet implemented.

### Competition Password
A development-only secret created with `/register` and used with `/login`. Microsoft mode disables this flow. Students never enter Microsoft passwords into Minecraft.

### Participant
An eligible person represented by one School Identity. The current Microsoft policy admits the configured student role; staff need explicit eligibility configuration. A Participant may hold no more than two active Entry memberships across different Categories, regardless of linked accounts.

### Team
One or two Participants who jointly own one Entry. Both members have equal build and entry-management authority after an invitation is accepted.

### Category
Exactly one of Journey, Place, or People.

### Journey
The Category for recreating a recognizable existing Hill building, landmark, exterior, parking area, pathway, or campus feature in a bounded outdoor Plot.

### Place
The Category for designing a Hill interior in a bounded Plot initialized from a selected Interior Template.

### People
The Category for modifying a private copy of the complete approved Cropped Campus Template to represent Hill's future.

### Entry
One competing project owned by a Team, assigned to exactly one Category, and associated with one Build Space. An Entry contains its title, description, Camera Poses, submission state, moderation state, and voting publication state.

### Entry Slot
One of the two active Entry memberships available to a Participant. Team membership consumes one Entry Slot for each Team member.

### Build Space
The protected editable environment assigned to an Entry. It is a Plot for Journey or Place and a Private Campus World for People.

### Plot
A bounded cuboid Build Space in a shared category world. Owners may modify it; visitors may observe it but may not modify it.

### Interior Template
A reusable Place shell such as a classroom, dorm room, study area, social space, dining area, or blank white-box room.

### Cropped Campus Template
The approved bounded voxelized Hill campus world used as the immutable source for People entries.

### Private Campus World
A private working copy of the Cropped Campus Template assigned to one People Entry.

### Owner Mode
The state in which an Entry owner is in Creative mode, may fly, and may modify the owned Build Space.

### Visitor Mode
The state in which a Participant may fly through or inspect a Build Space but cannot modify blocks, entities, inventories, fluids, redstone, or entry data.

### Authentication Lobby
The protected world and restricted session state before school verification succeeds. Development mode instead uses `/login` or `/register`.

### Exhibition Hub
The post-authentication ceremonial Hill 175 hall containing the Hill ram centerpiece, category selectors, rules, navigation, help, and archive displays.

### Pending Registration
A development-only reservation containing a nickname and password hash. Microsoft mode uses a five-minute browser challenge bound to a fresh game connection nonce, then a browser-only confirmation code entered with `/verify`.

### Account Link
The durable association between one verified game identity and one School Identity. Multiple Java/Bedrock identities may link to the same participant; a game identity cannot be automatically reassigned. Only one active game connection per participant is allowed.

### Camera Item
The spatial competition item used to create, replace, preview, or remove up to three Camera Poses for an Entry.

### Camera Pose
A saved world, position, orientation, and capture configuration used by the Capture Worker to render one submission image.

### Capture Worker
The controlled Minecraft client that visits saved Camera Poses, captures standardized images, and uploads them for moderation and voting.

### Submission
An Entry's title, description, up to three Camera Poses, generated images, and readiness state.

### Competition Phase
The server-wide lifecycle state controlling registration, building, locking, review, capture, voting, winner publication, and archival.

### Lock
The transition that makes Build Spaces and Submission fields read-only for Participants.

### Vote
One School Identity's current selection in one Category. A School Identity may hold at most one Vote per Category.

### Moderation Event
An auditable faculty or system action affecting a Participant, session, Team, Entry, Build Space, Submission, image, Vote, or access decision.

### Emergency Snapshot
A short-retention recovery copy created before a Participant-triggered reset, template change, or category change.
