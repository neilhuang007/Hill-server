# Hill 175 Competition Domain Glossary

## Terms

### School Identity
The immutable Hill-managed identity representing one eligible person. It is the authority for eligibility, entry limits, team membership, voting, moderation, and password recovery. It is distinct from the Minecraft nickname.

### Minecraft Nickname
The participant-selected Minecraft protocol username entered by the launcher. It is stored locally so the launcher can reuse it. It is linked to exactly one School Identity after registration. It is not proof of identity by itself.

### School Display Name
The full name supplied by Hill and displayed in the Minecraft server interfaces. It is hidden during anonymous voting. It is distinct from the Minecraft Nickname.

### Competition Password
A competition-specific secret created during registration and used with `/login` on subsequent joins. It is not a Hill password or Microsoft password. Successful password verification authenticates the current Minecraft session only.

### Participant
An eligible student or staff member represented by one School Identity. A Participant may hold no more than two active Entry memberships across different Categories.

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
The protected world and restricted session state used before `/login` succeeds or `/register` completes School Identity linking.

### Exhibition Hub
The post-authentication ceremonial Hill 175 hall containing the Hill ram centerpiece, category selectors, rules, navigation, help, and archive displays.

### Pending Registration
A temporary reservation containing a Minecraft Nickname and Competition Password hash that cannot become an Account Link until School Identity linking succeeds.

### Account Link
The one-to-one association between a Minecraft Nickname and a School Identity.

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
