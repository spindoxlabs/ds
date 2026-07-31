# Business Use Cases for Energy

> **Source** · Blueprint of the Common European Energy Data Space (CEEDS) v3.0, September 2025 › 3. Business Use Cases for Energy
> **Chapter** · 3, sections 3.1–3.6 · `Blueprint_CEEDS_v3.0.txt:417-1325`

The chapter presents the new business opportunities that are emerging in the energy sector, putting an emphasis on their business and technical feasibility. A set of high-level Business Use Cases (BUCs) has been defined by the cluster of energy data spaces projects, which exploit and fully rely on the use of data space technologies while considering the specific areas of the EU action plan "Digitalising the energy system". The BUCs describe the specific data exchanges that occur among the involved actors, and the source states that a crucial prerequisite for maximizing the advantages of the data spaces in the energy domain is the integration of data from diverse sources and with standardized data models and ontologies.

## Chapter scope and structure

The chapter defines **five** BUCs (`Blueprint_CEEDS_v3.0.txt:432`: "The five BUCs foster and support the large-scale deployment of the CEEDS, maximizing the benefits of data exchanges via the data spaces approach towards the enablement of new energy services."). They are listed in the source as:

- Use case #1 – "Collective self-consumption and optimized sharing for energy communities"
- Use case #2 – "Residential home energy management integrating Distributed Energy Resources (DER) flexibility aggregation"
- Use case #3 – "TSO-DSO coordination for flexibility"
- Use case #4 – "Electromobility: services roaming, load forecasting and schedule planning"
- Use case #5 – "Renewables O&M optimization and grid integration"

Figure 3 ("Identified reference use cases for CEEDS") renders the same five as segments of a ring around a "CEEDS use cases" hub, labelled "Use-case 1: Collective self-consumption and optimized sharing for energy communities", "Use-case 2: Residential home energy management integrating DER flexibility aggregation", "Use-case 3: TSO-DSO coordination for flexibility", "Use-case 4: Electromobility: services roaming, load forecasting and schedule planning", "Use-case 5: Renewables O&M optimization and grid integration".

Each BUC is presented "according to the general scope, the technical description of implemented services and the scenarios (i.e., the involved actors and the technical details of the data exchange instances, represented in sequence diagrams)". The source states: "It is worth highlighting that every actor of the BUCs corresponds to a data space participant, with the role of data provider or data consumer."

Section 3.6 "sheds light on how an interoperable dataspace facilitate the implementation of new EU grid codes regulation".

The energy system stakeholders the chapter names as needing interconnection are: consumers, local communities, TSOs, DSOs, Significant Grid Users (SGUs), multi-energy utilities, e-mobility operators, new flexibility service providers, Renewable Energy Sources (RES) developers and operators, and non-energy service providers.

### Table 2 — Summary of the BUCs

| Use Case ID | Use Case Title | Scope | Data Exchange Focus | Key Actors |
|---|---|---|---|---|
| #1 | Collective self-consumption and optimized sharing for energy communities | Residential and Commercial Energy Communities; energy sharing optimization | Data collection/sharing for flexibility and energy savings; non-intrusive load monitoring | Energy service companies, Energy traders, Market information aggregators, Resource aggregators |
| #2 | Residential home energy management integrating DER flexibility aggregation | Optimization of DER through data spaces for reducing grid congestions and critical peak prices | Real-time data exchange and streaming; leveraging IoT, edge computing and V2X interactions | Prosumers, DER operators, Flexibility Service Providers (FSP), Local energy management providers |
| #3 | TSO-DSO coordination for flexibility | Enhancing resilience and integration of large RES; non-cable solutions for congestion and voltage issues | Forecasting of loads and generation for resource scheduling; real-time control | TSOs, DSOs, DER operators, FSP |
| #4 | Electromobility: services roaming, load forecasting, and schedule planning | Optimization of EV charging infrastructure and services; predictive charging consumptions for grid management | Booking and scheduling of EV charging services; predictive analytics for EV charging demand | Charge Point Operators (CPO), e-Mobility Service Providers (eMSP), EV users |
| #5 | Renewables O&M optimization and grid integration | Optimizing Operation & Maintenance (O&M) of renewable energy assets; efficient integration of distributed energy sources into the smart grid | Leveraging data for fault detection, automated diagnosis, and maintenance; smart grid integration analytics | RES plant owners/operators, DSOs, Original Equipment Manufacturer (OEM), Component manufacturers, Data analytics service providers. |

### Table 3 — Data spaces objectives with respect to the BUCs

| Data Spaces Objectives | BUC #1: Collective Self-Consumption and Optimized Sharing | BUC #2: Residential Home Energy Management | BUC #3: TSO-DSO Coordination for Flexibility | BUC #4: Electromobility: Services Roaming, Load Forecasting, and Schedule Planning | BUC #5: Renewables O&M Optimization and Grid Integration |
|---|---|---|---|---|---|
| Educational Purpose and Research | Developing community models and energy sharing mechanisms | DER optimization strategies and technologies | Advanced grid management and flexibility solutions | EV public charging patterns and infrastructure optimization | Innovative O&M techniques for renewables integration |
| Data Exchange and Interoperability | Exchange of energy consumption and generation data | Real-time data streaming from IoT devices | Sharing of flexibility needs and resources | Interoperability between CPOs, eMSPs, and EMRSPs | Sharing of operational data for O&M optimization |
| Innovation and New Business Models | Novel community energy sharing models | Home energy management solutions, including V2X | Market-based approaches for flexibility | New business models for EV charging services | Data-driven O&M and grid integration solutions |
| Data Analysis and Visualization | Analysis of energy patterns for optimization | DER performance and optimization analytics | Forecasting and visualization of grid status | Analysis and forecasting of charging demand and infrastructure needs | Visualization of O&M insights and grid performance |
| Governance and Regulation | Governance frameworks for community energy sharing | Regulations for mass-produced DER integration | Coordination frameworks between TSOs and DSOs | Standards and protocols for electromobility services | Regulatory compliance for renewables integration |

## 3.1. Use case #1 - “Collective self-consumption and optimized sharing for energy communities”

### 3.1.1. Scopes

The general scope of this use case is the instantiation and operation of Jointly Acting Self-Consumers (JASC), Residential Energy Communities (RECs) and Commercial Energy Communities (CECs), aiming at the collective self-consumption, inside the communities, and the optimization of energy sharing, with the electrical system.

The specific objectives include:

- Size the technical components and conduct an economical evaluation for the deployment of energy communities, based on consumption and generation profiles as well as market data, weather data and the possibility of assets sharing business models.
- Provide the mechanisms for the collection and sharing of data, with appropriate granularity at the device level, of the energy consumption and generation, with the final goal of enabling flexibility and energy savings mechanisms.
- Extract approximated flexibility models for smart appliances (e.g., using non-intrusive load monitoring data), enabling an overall quantification of flexibility and estimation of energy savings from intelligent load control.

### 3.1.2. Description

The effective and large-scale deployment of energy communities, for collective self-consumption and regulated energy sharing, involves the optimization in both the network design phase (i.e., the size and location of distributed energy resources) and in the deployment of energy sharing mechanisms within the community and with the active role of electrical grid operators.

The use case includes **two optimization problems**:

1. The first aims at determining the optimal installed capacities in the REC / CEC, considering typical consumption profiles, availability of renewable energy sources, costs of technologies (both capital and operational cost) and opportunity costs of the community members (retailing tariff for the electricity consumed from the grid, and selling price for the electricity sold back to the grid).
2. The second considers the operation of the community constrained by the installed capacity from the first optimization problem, in particular its electrical energy sharing / trading, where the optimized dispatch of controllable energy resources (e.g., storage, thermal loads, electric vehicles) is obtained considering the opportunity costs of the community members, together with an internal electricity pricing mechanisms to settle the internal energy transactions among members, which can be computed with different approaches or algorithms, to be used to study different financial schemes for communities.

**Actors and data flow, as described in the source.** The data space environment enables the exchanges of data that are necessary for the execution of the optimization scenarios among actors, "whose roles are described in [3]" (reference [3] of the blueprint is "IDS-RAM 4 - Roles in the International data spaces"). In particular:

- The **Service Provider** offers, via its **broker**, the technical algorithms as services to which the **Service Consumer** has subscribed.
- Technical parameters (including the type of available devices, assets, and capacity constraints), pricing and financing specifications as well as consumption and generation data profiles are used as the inputs coming from the **Data Provider**.
- The consent for data sharing is obtained from the **Data Owner**.
- The data space **Clearing House** — "which is a service for logging data exchange transactions relevant for clearing and billing as well as usage control" — works as an intermediary to keep the log of the transactions.
- The output data are received by the **Service Consumers** and correspond to the optimal installed capacity, the estimated flexibility schedule and the pricing for internal and external transactions, differentiated according to the energy sharing mechanism.
- As an additional service, the provision of information regarding the required device maintenance is also included.
- The data exchange outputs allow improving the forecasts on available flexibility (i.e., aggregated demand side flexibility potential of the energy community).

The enablement of data space capabilities becomes key given the multiple stakeholders and service providers in this use case, often enrolled through a value-chain enabler (legal or digital platform with an established governance scheme). Thus, the need to procure a data exchange environment built around data sovereignty guarantees allows the translation from common legal contracts to smart contracts, which guides data exchange limits (i.e., usage policies) and the long-term and post-exchange traceability of all data and associated data transactions. Moreover, as exploring aggregated and anonymized models representing the profiles of the community members may be included in as a data monetization scheme, there is a real need for ensuring pre and post data exchange guarantees with identity verification and validation of the involved organizations, or the traceability of data flows as part of a digital passport for data as an asset.

### 3.1.3. Scenarios

The system encompasses **three sub-use cases, here named as scenarios**, each designed to address specific aspects of energy management within RECs and CECs:

**DER Sizing and Economic Evaluation of REC/CEC Business Model**: Users subscribe to data space for DER sizing and economic evaluation, combining real consumption profiles from historical data. They provide parameters, request data (e.g., real consumption profiles (historical data), and solve optimization problems to determine optimal capacities and schedules, aiming to maximize of collective self-consumption of energy.

**Estimation of Flexibility Potential and Energy Cost Savings from Thermal Domestic Loads**: Consumers subscribe via a Broker for flexibility estimation services. Data is requested, consent is obtained, and an optimization problem enhances the Electric Water Heater (EWH) operation. Output metadata, including flexibility potential, is transferred.

**Computation of Internal Transaction Price based on REC/CEC Operation**: Consumers subscribe to internal pricing and REC/CEC operation services via a broker. Data is requested, consent is obtained, and the selected pricing mechanism is executed. Output metadata, including energy transacted and prices, is transferred. The objective of this service is to simulate the operation of an internal market and extracts price curves that can be used to evaluate different business models (e.g., in terms of asset sharing) and the economic potential of communities for different stakeholders, such as inclusive communities for vulnerable consumers.

The source adds: "The use of a data space infrastructure allows trading data between organizations (i.e., the REC/CEC members and service providers, as developers of the running algorithms) while enforcing the data sovereignty stack."

#### Table 4 — Scenarios for the use case #1

| Scenario name, description | Actors | Triggering events | Pre-condition | Post-condition |
|---|---|---|---|---|
| DER sizing and economic evaluation of the REC / CEC business model | Consumer, Energy service company, Energy trader, Market information aggregator, Resource aggregator, FSP, Sub-meter data hub operator | Service consumer requests service | Consumption and generation profiles / time series available in the data space & tariff data | Information available about REC / CEC optimal sizing |
| Estimation of flexibility potential and energy savings from thermal domestic loads | Consumer, Energy service company, Energy trader, Market information aggregator, Resource aggregator, FSP, Sub-meter data hub operator | Service consumer requests service | Technical information from the EWH available; typical profiles or historical info about shower duration and start; sensor for outlet water | Data available about estimated energy cost savings and flexibility |
| Computation of energy price within the REC / CEC | Consumer, Energy service company, Energy trader, Market information aggregator, Resource aggregator, FSP, Sub-meter data hub operator | Service consumer requests service | Consumption and generation profiles / time series available in the data space & tariff data | Collective and individual operation costs or energy bills |

#### Figure 4 — Sequence diagram for the use case #1

Diagram title: **"Business Usecase 1 - REC Sizing and Planning"**.

Lifelines (verbatim, left to right): **Service Consumer** · **REC Service Provider** · **Data Cooperative Service Provider** · **Regulator Service Provider** · **PV Public Data**.

The diagram contains three fragments, one per scenario. The message sequence is identical in all three except for the computation step performed by the REC Service Provider.

Fragment 1 — **"DER Sizing and Economic Evaluation of the REC / CEC"**:

1. Service Consumer → REC Service Provider: `subscribes service`
2. Service Consumer → REC Service Provider: `provides consent`
3. REC Service Provider → Data Cooperative Service Provider: `request consumer data`
4. Data Cooperative Service Provider → itself: `validate data usage consent`
5. Data Cooperative Service Provider → REC Service Provider: `transfer data`
6. REC Service Provider → Regulator Service Provider: `request tarif data`
7. Regulator Service Provider → REC Service Provider: `transfer tarif data`
8. REC Service Provider → PV Public Data: `request PV Data`
9. PV Public Data → REC Service Provider: `transfer PV data`
10. REC Service Provider → itself: `Run Sizing mechanism`
11. REC Service Provider → Service Consumer: `receives data`

Fragment 2 — **"Estimation of flexibility potential and energy cost savings from thermal domestic loads"**: same sequence, with step 10 replaced by `Estimate Flexibility`.

Fragment 3 — **"Computation of energy price within the REC / CEC"**: same sequence, with step 10 replaced by `Simulation and price computation`.

> **Note:** `tarif` is the spelling used in the figure.

## 3.2. Use case #2 – “Residential home energy management integrating DER flexibility aggregation”

### 3.2.1. Scopes

Prosumers – whether residential, community, city, or industrial scale – are playing a new central focal role to enable cross-sectorial integration using their energy and flexibility data to actively contribute to a variety of flexibility markets. Moreover, the use of flexible DER located in residential environments allows to mitigate critical peak prices through wholesale markets as well as reduces TSO and DSO grid congestions. In this context new digital platforms are leveraging IoT, edge computing as well as federated cognitive cloud architectures with strategic digital features to optimally orchestrate DER through energy data spaces; this is pursued at the lowest voltage levels of the energy value chain, which includes home appliances and behind-the-meter DER and managed by resources operators and FSP that optimise the associated flexibility through their balancing portfolio. This approach requires rethinking the way data is generated from dedicated measurement devices, attached to DER, and exchanged throughout different federated actors of the electricity value chain: requirements involve real-time data exchange and streaming, taking advantage of a variety of domain-specific data exchange standards through consistent data space dictionaries.

### 3.2.2. Description

Future carbon-neutral houses will soon require providing new net-zero analytics as defined through the directive "Energy Performance of Buildings" and, hence, provide near real-time indications to homeowners about their home energy efficiency as well as their available flexible capacity to respond to grid congestions and emergency events. The home energy use will be continuously optimized while maximizing local PV self-consumption and minimizing electricity costs (associated with new real-time energy and flexibility prices). New flexible DERs are in the meantime introduced through the home environment, such as heat pumps, EV bidirectional chargers as well as home batteries; these devices require new local home edge optimization across these resources. New integration approaches are considered to automate and facilitate the associated integration, such as all-in-one residential home energy stations that integrate bidirectional EV and home stationary battery and solar PV (directly with DC technology, resulting in the default consumer data interfaces).

Local home energy management solutions are becoming essential building blocks to share residential DER data through multi-sided data exchange platforms, which are operated through distributed cloud infrastructures of OEM and integrate advanced real-time energy optimization as a service. Multi-sided platforms are accessed, on one side, by prosumers through their DER-specific app or high-level energy management apps while the other side is accessed by FSP accessing consumer data to enrol them (with their consent) in DER-specific flexibility programs.

This BUC is typically associated with large residential assets offering flexibility to homeowners, namely heat pumps, smart heating equipment, EV chargers (V1G and V2G) as well as residential hybrid inverters for solar and storage applications.

Reference DER data dictionaries are managed to enable plug-and-play registration of DER infrastructures in TSO-DSO flexibility markets; moreover, new real-time data stream across key actors of the energy flexibility value chain: from DER operator to energy community managers as well as with FSP and grid operators (TSOs and DSOs), hence automating associated residential DER transactions. The associated data space should allow managing all types of DER integrating the latest power electronics, edge computing and data streaming technologies to exchange relevant residential energy data (obtained from the main smart meter as well as from any other accessible DER submeters/dedicated measurement devices). The data space should be distributed through different federated cloud infrastructures and enable consent based on data exchanges across actors.

The referenced instrument is the directive "Energy Performance of Buildings" (https://energy.ec.europa.eu/topics/energy-efficiency/energy-efficient-buildings/energy-performance-buildings-directive_en).

### 3.2.3. Scenarios

This BUC defines **nine** scenarios. Table 5 lists them with their actors; unlike the other scenario tables in this chapter it has no *Triggering events*, *Pre-condition* or *Post-condition* columns.

#### Table 5 — Scenarios for the use case #2

| Scenario name, description | Actors | Additional information |
|---|---|---|
| Residential energy and carbon footprint monitoring | Prosumer, Resource aggregator | |
| Residential DER registration by DER operators | Prosumer, Resource aggregator, Consent administrator, Flexibility register, Flexible product qualifier | Registration consists in messages to registers customers in the DSO flexibility register. |
| Residential home energy optimization | DER, Local energy management, Weather forecast provider, FSP, Balancing responsible party | |
| Residential baseline calculation | Data provider, Resource provider, Resource aggregator, Balancing service provider, FSP | Provision of baseline data calculated by the service provider or the final customer, also based on weather/carbon/other data. |
| Residential flexibility intraday calculation | Data provider, Resource provider, Resource aggregator, Balancing service provider, FSP | |
| Residential flexibility bidding | Balancing service provider, FSP, Market operator, TSO, Flexibility buyer | Onboarding to market platform (and activation tests/product prequalification). Data exchange and communication requirements need to be tested for balancing services. |
| Residential flexibility activation | Market operator, TSO, Flexibility buyer, Balancing service provider, FSP, Resource provider, DER, Prosumer | When flexibility is activated (either through a bare execution of a bid, or via set points), a controllable unit can receive these signals either via the Service Provider or directly from the System or Market Operator. Service Providers may use the Kafka-based streaming infrastructure for both communication with the market, but also with their units under control. |
| Residential flexibility observability | Market operator, TSO, DSO, Resource aggregator, Resource provider, DER | After the delivery phase, measurements at different points need to be transferred to the Flexibility Registry Operator, to make them in turn available to the Settlement Responsible Party for service validation and perimeter correction. |
| Residential flexibility transaction management | Flexibility settlement party, Metered data responsible, Metered data collector, Balancing service provider, FSP, Resource provider, DER, Prosumer | |

#### Figure 5 — Sequence diagram for the use case #2

Lifelines (verbatim, left to right): **System Operators** · **Flexibility Service Provider** · **Technical Aggregator** · **Prosumer/DER Owner**.

Fragment 1 — **"Normal operation (Pre-flexibility notification)"**:

1. Technical Aggregator → System Operators: `DER Registration`

Fragment 2 — **"Flexibility Bidding & Event Activation"**:

1. System Operators → Flexibility Service Provider: `Flexibility Market Gate Opening`
2. Flexibility Service Provider → Technical Aggregator: `Flexibility Price Forecast`
3. Prosumer/DER Owner → Technical Aggregator: `Near Real-time Baseline Calculation`
4. Technical Aggregator → Flexibility Service Provider: `Aggregated Baseline Nomination`
5. Prosumer/DER Owner → Technical Aggregator: `DER Flexibility Estimation`
6. Technical Aggregator → Flexibility Service Provider: `Portfolio Flexibility Calculation and Bidding`
7. System Operators → Flexibility Service Provider: `Flexibility Market Gate Clearing`
8. Flexibility Service Provider → Technical Aggregator: `Portfolio Activation Event`
9. Technical Aggregator → Prosumer/DER Owner: `DER Control Confirmation to Relevant Sites`

Fragment 3 — **"Flexibility Observation"**:

1. Prosumer/DER Owner → Technical Aggregator: `FlexDER ex ante Event Delivery Observability`
2. Prosumer/DER Owner → itself (self-message)
3. Technical Aggregator → Flexibility Service Provider: `Ex ante Aggregated Telemetry Streaming`
4. Flexibility Service Provider → System Operators: `Grid Power Flow Optimization`
5. Prosumer/DER Owner → Technical Aggregator: `FlexDER ex post Event`
6. Technical Aggregator → Flexibility Service Provider: `Aggregated DER Portfolio Delivery Verification`
7. Flexibility Service Provider → System Operators: `Flexibility Event & Settlement`
8. System Operators → itself: `Evaluation of Imbalance Penalties`
9. Flexibility Service Provider → Technical Aggregator: `Penalties for Non-delivery`
10. Flexibility Service Provider → itself: `DER Revenue Settlement`

## 3.3. Use case #3 - “TSO-DSO coordination for flexibility”

### 3.3.1. Scope

With the increasing decentralization and decarbonization of the energy system, TSOs and DSOs are faced with the challenge of ensuring the resilience of the energy system, while enabling the integration of large RES to contribute to the achievement of ambitious RES deployment targets. The uncertainty of loads and generation flows poses increased challenges over-optimized network operations. Congestions and voltage issues that have been typically addressed with costly network upgrades need to be tackled with smarter, cheaper, non-cable alternative solutions that flexible DER offers through their power electronics interfaces and technologically existing aggregation potential. Active network management regimes for network control need to be developed, which require advanced forecasting of loads and generation for resource scheduling and real-time control. Moreover, a variety of analytics are necessary to ensure that appropriate measures exist to satisfy compliance with evolving reliability standards and security of supply. In their role as system operators, TSOs and DSOs are required to explore, evaluate, and deploy non-network alternatives that include the operation of market-based approaches such as frequency containment and reserves.

The development of new market-based approaches shall be non-discriminatory and services might be offered from all eligible participants (either aggregated or direct end-users) at different voltage levels, while the operation of the transmission and distribution networks shall be performed collaboratively between TSOs and DSOs to ensure synergetic service provision and avoidance of conflicting actions while co-optimizing the operation of both systems (distribution-transmission-national) and reducing the overall OPEX. As electricity network management evolves towards more collaborative management structures, it is of utmost importance that TSOs and DSOs are involved in bilateral data-sharing agreements (facilitated by energy data spaces) towards exchanging flexibility requirements, enabling the identification of critical operational events at both levels of electricity grid operation and allowing for their common criticality prioritization while identifying available flexibility resources. This is pursued through federated flexibility registers, as defined through the new demand side flexibility code, towards ensuring the optimal operation of power grids under evolving real-time conditions via optimal collaborative operational scheduling, maximisation of capacity usage, activation of offered flexibility as well as deployment of flexible connection agreements. System operators also need to engage in data sharing with FSP (as identified in the use case #2) towards gaining increased visibility over available flexibility sources and proper clusters of them based on information shared by the relevant actors.

### 3.3.2. Description

The exploitation of flexibility, stemming from generation, demand, storage and EV assets, for solving network issues, such as balancing and congestion, is not a novel idea. However, on the one hand the sparsity of adequate real-time information about the available flexibility and on the other hand the fact that most flexible assets and several sources of flexible generation are connected to the distribution system, poses significant barriers to the efficient exploitation of the flexibility by the transmission system operator. To this end it is of utmost importance that novel approaches (data-driven and intelligence-enabled) are defined, at first for the real-time or near-to-real-time aggregation of the available flexibility provided by distributed energy resources located in the distribution network. Since the majority of the resources located in the distribution system are small-scale, they need to be aggregated to be efficiently included in the operational planning of either DSO or TSO. Moreover, tools enhancing the fast and efficient coordination between TSO and DSO should be developed, so that flexibility from the distribution system to be transferred to the TSO for balancing the system or solving network issues.

In fact, electricity networks are progressively being dominated by small, dispersed prosumers (as also highlighted in use case #2), not only in terms of number but also in terms of criticality for the system resilience since they are associated to the ever growing number of small-scale DERs connected to the network, that continuously expand the energy system "edge", in terms of controllability and operational complexity. The progressive decentralization, which is also accompanied by the introduction of new digitalized assets (EVs, IoT, batteries), poses significant challenges for the resilience of the system, while introducing increased uncertainty in traditional control routines, given the stochastic and intermittent character of renewable generation and the new control variables (not currently addressed in existing tools for the system management) introduced by new assets. Under these circumstances, energy systems need to evolve towards integrated ecosystems and, more specifically, integrated data value chains, to enable the data-driven optimization at system and DER level in a coordinated manner, by stepping on trustful data (intelligence) sharing models facilitated by energy data spaces. Such models and approaches will increase stakeholders' data outreach, enhance their intelligence and facilitate the realization of innovative energy services and collaboration models for improving networks operations in a resilient manner by utilizing the untapped flexibility potential of small-scale dispersed DERs.

As technology advances and becomes more affordable, prosumers and DER owners are no longer perceived as passive elements of the energy system, but are transforming themselves into active nodes that can effectively contribute to its optimized operation since:

- they comprise in a huge source of flexibility able to support distribution and transmission system operators with the needed services to balance demand & supply and manage power quality and system resilience, and, at the same time,
- they are associated with the generation of vast amounts of asynchronous streamed-data, spanning smart metering and sub-metering information, IoT device information (sensing/control), distributed generation (RES), storage, building systems (heating/ cooling) and electric vehicle data, becoming more and more essential for improving observability and orchestrating the resilient operation of a decentralized and complex energy system that effectively achieves the decarbonization advantages that come with the increasing penetration of RES and the progressive electrification of the mobility and building sectors.

Hence, it becomes obvious that the real value of data produced by prosumers and DERs at the edge of the energy system (and beyond it) is hidden in the (real-time) sharing of such (previously non-reachable) information with the rest of the energy data value chain stakeholders that their operations are directly or indirectly linked to prosumers' distributed assets. The value of energy data spaces and the data sharing functions enabled through them. for network operators, lies on the fact that they can further optimize the stability and resilience of their network through enhanced asset observability, improved forecasting and flexibility analytics resulting from detailed prosumer and DER data.

The coordination between TSOs and DSOs is critical for effective flexibility management, as identified in the recent flexibility code deployment. Both types of operators need to work together to prioritize and address the flexibility needs in their respective networks. To achieve this, improved forecasting approaches and flexibility analytics are needed, as well as coordinated and collaborative scheduling and dispatch practices and tools, for the accurate identification and effective prioritization of critical events expected to occur across the electricity grid. Both System Operators will need to obtain access to previously non-reachable data from DERs across their networks (including local demand data from flexible loads, RES generation data, along with flexibility-relevant data from storage assets/ inverters and associated short- and mid-term forecasts) and fuse them with their own SCADA and metering data so that they can effectively forecast their flexibility requirements, match them to the available flexibility offered by the variety of prosumers, DERs and other flexible assets, prioritize procurement strategies (according to the criticality of events and based on the transparent sharing of operational data and flexibility requirements among them, through the CEEDS) and successfully dispatch the respective signals to ensure the end-to-end resilience of the energy system in the most favourable economic terms.

### 3.3.3. Scenarios

§3.3.3 consists of Table 6 and Figure 6; the source states no scenario count for this BUC. Table 6 lists **six** scenario rows.

#### Table 6 — Scenarios for the use case #3

| Scenario name, description | Actors | Triggering events | Pre-condition | Post-condition |
|---|---|---|---|---|
| Performant data search across federated data spaces | Data asset consumers (role obtained by TSOs, DSOs and FSPs) | A party needs to create a service without having at its disposal all the necessary data assets | Raw data, analysis results, reports, visualizations allowing for automated consumption. | The party is able to consume the data asset that has been acquired based on a valid asset contract. |
| Sharing, trading and bartering of raw and derivative data assets, available in federated data platforms/ hubs (incl. OEM platforms) | Data asset providers, Data asset consumers (both roles obtained by TSOs, DSOs and FSPs involved in bilateral data sharing) | Request for access to previously non-reachable data | 1) Raw data, analysis results, reports, visualizations allowing for automated consumption; 2) Availability of mechanism to search for data and other data-based assets | A data asset (raw data or computations on data in the form of analysis results, reports or visualizations) is shared between two or more data value chain stakeholders |
| AI-enabled Grid-level energy demand and generation forecasting | DSOs, TSOs | On demand by the operator | 1) Metering and acquired DER data for training and executing the respective forecasting models; 2) Access granted to AI analytics results referring to individual and aggregated DERs | Consolidated forecasts of demand and generation across the entire network |
| AI-enabled Grid-level flexibility profiling and forecasting | FSP | On demand by the FSP | DER data for training and executing the respective analytics models | Detailed flexibility profiles and forecasts at individual DER and aggregated levels |
| Operational events identification in the short and mid-term | DSOs, TSOs | On demand by the operator | 1) Detailed data for the existing transmission and distribution network topology and infrastructure; 2) Availability of short/ mid-term Demand and Generation forecasts | Identification of anticipated critical operation events and their occurrence probability |
| Short-/ Mid-term Network Operation Planning | DSOs, TSOs | On demand by the operator | 1) Detailed data for the existing transmission and distribution network topology and infrastructure; 2) Flexibility profiles and short/ mid-term forecasts | 1) Definition of margins and requirements for flexibility to address the anticipated events; 2) Specification of the flexibility sources to effectively tackle the identified critical operation events |

> **Ambiguous:** Table 6 lists six scenario rows while Figure 6 renders four fragments, and the two do not correspond one-to-one. See *Open questions*.

#### Figure 6 — Sequence diagram for the use case #3

Lifelines (verbatim, left to right): **DSO/TSO** · **Prosumer/DER Owner** · **Analytics Service Provider** · **Digital Twin Service Provider** · **TSO-DSO Flexibility-based Operational Scheduling Service Provider**.

Fragment 1 — **"Searching, Sharing, and Trading Data"**:

1. DSO/TSO → Prosumer/DER Owner: `Search for and Request of Prosumer/DER Data`
2. Prosumer/DER Owner → DSO/TSO: `Provision of Prosumer/DER Data`

Fragment 2 — **"Grid-level Energy Demand and Generation Forecast"**:

1. DSO/TSO → Analytics Service Provider: `Request for Demand/Generation/Flexibility Forecast`
2. Analytics Service Provider → DSO/TSO: `Request for Demand/Generation/Prosumer/DER Raw Data`
3. DSO/TSO → Analytics Service Provider: `Provision of Demand/Generation/Prosumer/DER Data`
4. Analytics Service Provider → DSO/TSO: `Demand/Generation/Flexibility Forecasts`

Fragment 3 — **"Operational Event Identification"**:

1. DSO/TSO → Digital Twin Service Provider: `Request Identification of Critical Events`
2. Digital Twin Service Provider → DSO/TSO: `Request GIS and Network Topology Data`
3. DSO/TSO → Digital Twin Service Provider: `Provision of GIS and Network Topology Data`
4. Digital Twin Service Provider → DSO/TSO: `Provision of Critical Events`

Fragment 4 — **"Short-/Mid-term Network Operation Planning"**:

1. DSO/TSO → TSO-DSO Flexibility-based Operational Scheduling Service Provider: `Request for Optimized Flexibility-based Scheduling`
2. TSO-DSO Flexibility-based Operational Scheduling Service Provider → DSO/TSO: `Request for the Short-term Flexibility Requirements`
3. DSO/TSO → TSO-DSO Flexibility-based Operational Scheduling Service Provider: `Short-term Flexibility Requirements`
4. TSO-DSO Flexibility-based Operational Scheduling Service Provider → itself: `Prioritization and Optimized Scheduling`
5. TSO-DSO Flexibility-based Operational Scheduling Service Provider → DSO/TSO: `Provision of Flexibility Activation Schedules`

#### Data needs for use case #3

"Regarding the data needs for the realization of use case #3, the following datasets are needed:"

- GIS data of MV/LV lines including information about electrical connection (cable or overhead line, length, type, routing).
- Transformer electrical data: Capacity (nominal apparent power), voltage primary & secondary, degree of load Velander's formula constants, etc.
- SCADA Data: Power grid measurements for voltage and current, power factor, tap changer positions at the 10 kV side of the 60/10 kV feeders, frequency measurements, active and reactive measurements for power generators on 10 kV feeders.
- AMI Data - Consumers Smart metering data from MV & LV telemetered consumers (Active+, Reactive or Q1 or both).
- AMI Data - Producers Smart metering data from MV & LV telemetered producers PV/ Wind (Active-, Active+, Reactive or Q1 or both).
- Metering data for non-telemetered: Aggregated metering data for non-telemetered MV & LV consumers & producers.
- Grid-level Flexibility Forecasting: Grid-level flexibility forecasting on a 15-minute interval prior to real-time operation.
- Grid-level Energy Demand & Generation Forecasting: Grid-level Demand and generation Forecasting on a 15-minute interval prior to real-time operation.
- Total generation: Network peak and average total generation.
- Total demand: Network peak and average total demand.
- Congestion problems: Investigation and detection of network constraints violations.
- Flexibility requirements: Based on the detected congestions.
- Storage device operational data.
- Flexibility offers: Offers of the available flexibility at each time instant/period from the FSPs.

## 3.4. Use-case #4 - “Electromobility: services roaming, load forecasting and schedule planning”

### 3.4.1. Scopes

"Given the peculiarity of this sector in the energy domain, the interfaced actors are introduced; they correspond to:"

- **Charge Point Operator (CPO)**: party responsible for provisioning and operating EVCI (EV Charging Infrastructure), optimizing the costs & revenues from charging sessions (on the behalf of one or several EVCI owners).
- **e-Mobility Service Provider (eMSP)**: party responsible for providing high-value service related to the use of an EV (e.g. booking service). All these services require a subscription to the eMSP from the EV user. Users can access to the services with an application (System actor: e-Mobility Service Provider Application). Moreover, this actor can also exchange data on consumption schedules with DSOs and TSOs and provide flexibility services to the grid.
- **Electro Mobility Roaming Service Provider (EMRSP)**: party responsible for offering a universal intermediation service between CPOs and eMSP. It can also offer interface services with other EMRSPs, thereby broadening the range of responses available to subscribed eMSPs.
- **Electric Vehicle User (EVU)**: person or legal entity using the vehicle and providing information about driving needs and consequently influencing charging patterns.
- **AI Service Provider**: party responsible for provisioning AI data processing services.

"In the electromobility context, this BUC aims to address the following objectives:"

- Offer a standardized roaming booking service for electric vehicle users and Charing Point Operators (CPOs) across Europe.
- Provide DSOs/TSOs with charging consumptions schedule based on CPOs' charging schedules and reserved powers, to enhance the accuracy of system operators' forecasts and planned operations.
- Provide flexibility services to the DSOs/TSOs to optimise smart grids management.

### 3.4.2. Description

In this use case, an EVU who wants to book a charging service must connect to an eMSP, as an application or platform. On this application, he is going to have visibility on the existence of infrastructures, their availability, and will be able to reserve a charging point.

Once connected to the application, users can search for available charging points according to their criteria of location, time and technical specifications for charging. Moreover, the user can compare the different rates applied according to operator and charging criteria.

Furthermore, the user can then reserve a charging slot by specifying the information required for accessing the charging pool, charging his car, and paying for the session (physical characteristics, means of authentication at the charging point, etc.) He/she can access an estimate of the final charge price (calculation based on the selected criteria and provided details). Once the charge has been completed, the user will be able to access his detailed invoice from the eMSP application and will be charged the final amount due. The aim is to make this service available throughout Europe, aggregating all CPO services and facilitating access to them for all electric vehicle users similarly to the mobile roaming services.

In addition, the data on the energy consumption, associated with the scheduled and performed charging session, is exchanged between the EMSP and the DSO/TSO to improve the load forecasting and electrical grid operations. Equally, the DSP/TSOs can send flexibility orders to EMSP to modify the charging schedule. Hence, this use case aims to be the bridge between the mobility and energy data space providing flexibility from EVs to TSO/DSOs for optimising the management of smart grids.

**Pre-requisites.** "All in all, this use case shares certain pre-requisites related with a European data space, starting from the initialisation of European data space connectors. This macro activity corresponds to the fact that the EMSP (in charge of the booking of charging services), the CPO and the EMRSP are registered on the marketplace of a European data space, the EMRSP has subscribed to the CPO's service (and that the CPO has accepted it), and the EMSP has subscribed to the EMRSP's service (and that the EMRSP has accepted it). Then, the EMRSP exchange its tariffs with CPO and EMSP."

### 3.4.3. Scenarios

The use case #4 is further divided into **two** scenarios, namely the EV booking roaming service and the EV flexibility service.

#### Table 7 — Scenarios for the use case #4

| Scenario name, description | Actors | Triggering events | Pre-condition | Post-condition |
|---|---|---|---|---|
| EV Booking Roaming Service | EVU, eMSP, EMRSP, CPO | Action of the EVU in the eMSP app. | 1) EVU is authenticated to the eMSP App; 2) eMSP is registered as a consumer of EMRSP services; 3) CPOs are registered as providers on EMRSP app;(Optionally) EMRSP are registered as provider of other EMRSP | 1) Reservation contract 2) DSO/TSO receives data on energy consumption |
| EV Flexibility Service | TSO/DSO EMSP | TSO/DSO detects a flexibility need in the grid. | 1)The TSO/DSO has received the baseline data on energy consumption from the EMSP | 1)EMSP sends the modified charging schedule of EVs. 2) DSO/TSO receives the updated data on energy consumption |

#### Figure 7 — Sequence diagram for the use case #4 - EV Booking Roaming Service

Lifelines (verbatim, left to right): **EV User** · **e-Mobility Service Provider** · **e-Mobility Roaming Service Provider** · **Charging Point Operator**.

Fragment 1 — **"Charging Point Location Retrival"**, containing a `loop` fragment with guard `[every X s]`:

1. e-Mobility Roaming Service Provider → Charging Point Operator: `Request Bookable Pool Location`
2. Charging Point Operator → itself: `Compute Pool Location`
3. Charging Point Operator → e-Mobility Roaming Service Provider: `Return Pool Locations`
4. e-Mobility Roaming Service Provider → itself: `Store Pool Locations`

Fragment 2 — **"Request for Charging Point Interaction by EV Users"**:

1. EV User → e-Mobility Service Provider: `Request Charging Point Location/Time Slots/Booking/Cancellation`
2. e-Mobility Service Provider → e-Mobility Roaming Service Provider: `Request Charging Point Location/Time Slots/Booking/Cancellation`
3. e-Mobility Roaming Service Provider → itself: `Selecting CPO Service/ Internal Service Call`
4. e-Mobility Roaming Service Provider → Charging Point Operator: `Request Charging Point Location/Time Slots/Booking/Cancellation`
5. Charging Point Operator → itself: `Compute/Check Requested Service`
6. Charging Point Operator → e-Mobility Roaming Service Provider: `Return Response (OK/NOK/Data)`
7. e-Mobility Roaming Service Provider → itself: `If necessary: Aggregate Data`
8. e-Mobility Roaming Service Provider → e-Mobility Service Provider: `Return Response (OK/NOK/Data)`
9. e-Mobility Service Provider → EV User: `Return Response (OK/NOK/Data)`

Fragment 3 — **"Booking Cancellation by e-Mobility Service Provider"**:

1. e-Mobility Service Provider → e-Mobility Roaming Service Provider: `Cancel Booking`
2. e-Mobility Roaming Service Provider → itself: `Selecting CPO Service/ Internal Service Call`
3. e-Mobility Roaming Service Provider → Charging Point Operator: `Cancel Booking`
4. Charging Point Operator → itself: `Check Cancellation`
5. Charging Point Operator → e-Mobility Roaming Service Provider: `Return Response (OK/NOK)`
6. e-Mobility Roaming Service Provider → e-Mobility Service Provider: `Return Response (OK/NOK)`
7. e-Mobility Service Provider → EV User: `Optional Notification`

Fragment 4 — **"Booking Cancellation by Charging Point Operator"**:

1. Charging Point Operator → e-Mobility Roaming Service Provider: `Notify About Cancellation`
2. e-Mobility Roaming Service Provider → itself: `Select e-Mobility Service Provider`
3. e-Mobility Roaming Service Provider → e-Mobility Service Provider: `Notify About Cancellation`
4. e-Mobility Service Provider → EV User: `Notify About Cancellation`

Fragment 5 — **"Booking Summary"**:

1. Charging Point Operator → itself: `Detect Booking Expiry/ End of Charge`
2. Charging Point Operator → e-Mobility Roaming Service Provider: `Send Booking Summary`
3. e-Mobility Roaming Service Provider → itself: `Select e-Mobility Service Provider`
4. e-Mobility Roaming Service Provider → e-Mobility Service Provider: `Send Booking Summary`
5. e-Mobility Service Provider → EV User: `Send Booking Summary`

> **Note:** `Retrival` is the spelling used in the figure.

#### Figure 8 — Sequence diagram for the use case #4 - EV Flexibility Service

Lifelines (verbatim, left to right): **DSO/TSO** · **e-Mobility Service Provider** · **AI Service Provider** · **Charging Point Operator**.

Fragment 1 — **"Flexibility Request by DSO/TSO"**:

1. DSO/TSO → e-Mobility Service Provider: `Flexibility Request`
2. e-Mobility Service Provider → AI Service Provider: `Request Optimal Charging Profile for each CPO`
3. AI Service Provider → e-Mobility Service Provider: `Optimal Charging Profiles`
4. e-Mobility Service Provider → Charging Point Operator: `Send Power Modulation Demand`
5. Charging Point Operator → e-Mobility Service Provider: `Confirm Effective Power Modulation`

Fragment 2 — **"Billing of Flexibility Requests"**:

1. e-Mobility Service Provider → DSO/TSO: `Bill for Flexibility Request`
2. DSO/TSO → e-Mobility Service Provider: `Payment`
3. e-Mobility Service Provider → Charging Point Operator: `Share Payment`

## 3.5. Use case #5 – “Renewables O&M optimization and grid integration”

### 3.5.1. Scopes

The main challenges of renewable energies for getting larger deployment are cost competitiveness and smart grid integration. Therefore, the scopes of this use case are:

1. Develop more robust algorithms for optimizing the O&M of renewable energy assets by leveraging data from multiple renewable energy plant owners. This will allow a more reliable and earlier fault detection, automated diagnosis and maintenance prescription resulting in reduced operation and maintenance costs (OPEX).
2. Develop data analytics to enable efficient integration of distributed energy sources into the smart grid by monitoring data from different actors such as consumers and producers and data from the grid itself anticipating potential issues, like congestion or voltage volatility, impacting on quality and security of service. This can facilitate decision making on the optimal location and size of renewable resources in the overall system.

### 3.5.2. Description

An optimized O&M of renewable assets along their lifetime is key to reduce the Levelized Cost Of Energy (LCOE) by increasing the Performance Ratio (PR) and reducing O&M costs and Weighted Average Cost of Capital (WACC). However, nowadays data are normally kept in silos within companies. This is one of the main blockers for AI since the ability of the algorithms to learn and generalize is limited by the company's data, which generally covers a limited range of possible operating conditions. Data Spaces enable access to a wider range of information than the one related to one single portfolio, enhancing the generalization capacity of AI algorithms for different operating conditions. Furthermore, in some domains, such as wind energy, some relevant actors, such as component manufacturers (Tier 2-3 categories), ICT companies, SMEs and academia do not have access to operational data, causing the block of their capacity to improve existing products and develop innovative digital services.

Moreover, high penetration rates of Renewable Energy Sources require special measures by the DSO to ensure the quality and security of energy supply. In this context, it is crucial to develop innovative digital services that leverage existing data from different stakeholders (prosumers, DSO, aggregator) to optimise the power flows in the gird. Consequently, it is necessary to foster data exchange amongst different actors of the energy system, while ensuring data security, privacy and sovereignty.

**Actor categories.** "In this BUC, the category of data providers includes RES plant owners, RES plant operators, OEMs, DSOs and consumers/producers, while the data users are component manufacturers (Tier 2-3 categories) and data analytics service providers."

### 3.5.3. Scenarios

In terms of the crucial datasets for exchange, this encompasses SCADA data for RES operation, meteorological data, smart grid data, and prosumer energy consumption (smart meter) data.

Regarding the extent of data exchange, it varies with the specific application. For O&M optimization purposes, the scope is global, aiming to gather real operational data from similar assets in diverse operating conditions worldwide. On the other hand, for smart grid integration, the scope is more localized or regional. The majority of the required datasets are proprietary and, in some instances, contain business-critical information. Additionally, certain datasets, such as prosumer data, may include personal information that needs to comply with GDPR. Notably, meteorological data is typically open source.

Concerning the willingness of data providers to engage in a European data space and share data across borders, this largely depends on the renewable technology involved. For example, solar PV data are typically owned by PV plant owners/operators who are open to sharing data. Conversely, in the wind energy sector, this data is predominantly owned by OEMs who are less inclined to share. This difference is because the wind energy sector is shifting its business model from selling wind turbines to provide O&M services, and data is a key competitive advantage to provide this type of services.

The data is exchanged through the Common European Energy Data Space through the so-called connectors ensuring data privacy, security and sovereignty. This data is used to provide energy services by processing raw data through data-driven AI algorithms. These services include for example, RES O&M optimization service, Digital Twins for RES assets and Smart Grid, Prosumer Energy Demand/Generation forecast, smart grid reinforcement planning service, etc.

#### Table 8 — Scenarios for the use case #5

| Scenario name, description | Actors | Triggering events | Pre-condition | Post-condition |
|---|---|---|---|---|
| RES O&M optimization | OEM, RES plant owners/operators, TIER2-3 component manufacturer, Data analytics service providers | RES plant owners/ operators requests service | RES operational data available in the data space | Early detection of failures, optimized maintenance schedule, optimal operation prescription. |
| RES smart grid integration | RES plant operators, prosumers, DSO | DSO requests service | Smart meter data and RES operational data available in the data space. | Anticipate potential issues (congestion or voltage volatility, etc.) and prescribe corrective actions. |
| Optimal RES sizing (prosumer/community) | Consumer/Producer, Data analytics service providers, DSO | Customer/ Community request | Generation, consumption and storage data available, geographic parameters, EV and prices | Provide optimal size for RES integration |
| DSO resources optimal location | DSO, Consumer/ Produces, Data analytics service providers | DSO Request | Generation, consumption and storage data available, grid model (info for digital twin) grid information (existing problems), assets that can be installed | Provide optimal location for DSO resources |

#### Figure 9 — Sequence diagram for the use case #5

Lifelines (verbatim, left to right): **DSO** · **Prosumer/DER Owner** · **Analytics Service Provider**.

Fragment 1 — **"RES O&M optimization"**:

1. Prosumer/DER Owner → Analytics Service Provider: `Send SCADA Data`
2. Prosumer/DER Owner → Analytics Service Provider: `Send Meteo Data`
3. Analytics Service Provider → Prosumer/DER Owner: `Alarm of Potential Failure`
4. Analytics Service Provider → Prosumer/DER Owner: `Provide Optimized Maintenance Schedule`

Fragment 2 — **"RES Smart Grid Integration"**:

1. DSO → Analytics Service Provider: `Send Smart Grid Operation Data`
2. DSO → Analytics Service Provider: `Send Smart Meter Data`
3. Prosumer/DER Owner → Analytics Service Provider: `Send SCADA data`
4. Analytics Service Provider → DSO: `Notification of Potential Issues (Congestion, Voltage Violation, etc.)`
5. Analytics Service Provider → DSO: `Prescribe Corrective Actions`

Fragment 3 — **"Optimal RES Sizing"**:

1. DSO → Analytics Service Provider: `Send Energy Price Data`
2. DSO → Analytics Service Provider: `Send Smart Meter Data`
3. DSO → Analytics Service Provider: `Send GIS Data`
4. Prosumer/DER Owner → Analytics Service Provider: `Send Generation Data`
5. Prosumer/DER Owner → Analytics Service Provider: `Send Storage Data`
6. Analytics Service Provider → DSO: `Provide Optimal Size of RES`

Fragment 4 — **"DSO Resources Optimal Location"**:

1. DSO → Analytics Service Provider: `Send Smart Grid Model Data`
2. DSO → Analytics Service Provider: `Send Smart Meter Data`
3. Prosumer/DER Owner → Analytics Service Provider: `Send Generation Data`
4. Prosumer/DER Owner → Analytics Service Provider: `Dend Storage Data`
5. Analytics Service Provider → DSO: `Provide Optimal Location for DSO Resources`

> **Note:** `Dend Storage Data` is the label used in the figure.

## 3.6. Network codes requirements

A crucial area where energy data spaces can potentially act as a game changer is in the implementation of new rules mandated by the **network code on demand response**; particularly relevant for the presented use cases #1 "Collective self-consumption and optimized sharing for energy communities" and #2 "Residential home energy management integrating DER flexibility aggregation".

Experts from the **EU DSO Entity** and **ENTSO-E** are collaboratively drafting the legal text proposal in close cooperation with European stakeholders. Market actors are increasingly calling for efficient value-stacking options between market platforms and various participants on the demand side. To gain a better understanding of the matter, it is worthwhile to review how future legislation is likely to define specific concepts and allocate responsibilities.

**Figure 10 — Definitions as basis for rules on demand response.** The figure shows three connection points (`CP`) along a grid line, each serving a house; two houses contain an `EMS`. Individual devices (heat pump, battery/storage, EV) are outlined per a colour code shown in the figure legend: *technical resource*, *controllable unit*, *service providing unit*, *service providing group*. Three service providing groups are labelled `SPG1`, `SPG2` and `SPG3`, each spanning assets across more than one household.

To allocate responsibility in the future energy scenario, it is necessary to categorize key assets that play active roles in the market mechanisms under transformation. Referring to Figure 10, assets will be categorized as follows:

- **"Technical resource"**: an individual power generation, energy storage, or demand module.
- **"Controllable unit"**: a single technical resource or a group of technical resources behind the same connection point, provided that these technical resources can be collectively controlled. In this context, the controllable unit remains under the full sovereignty of the final customer, who has the authority to decide which aggregator or service provider will market the flexibility of the asset.
- **"Service providing unit" (SPU)**: a single controllable unit or a group of controllable units, a **"service providing group" (SPG)**, connected to the same connection point. SPUs and SPGs are defined by the service provider to deliver local or balancing services.
- **"Service provider" or "aggregator"** is a market participant with a legal or contractual obligation to supply local or balancing services from at least one SPU or SPG.

With this conceptual framework as a foundation, regulations govern complex services, and the markets associated with them. High-level real-time monitoring requirements will need to be managed by service providers. Simultaneously, the provision of local services must be coordinated and potentially constrained by system operators to avoid violating grid limitations, through local congestion-based markets and, potentially, flexible connection agreements. Submetering, together with embedded measurement devices in control unit equipment, will be integrated into the European regulatory framework, and multiple FSP, as well as multiple suppliers, will be permitted to operate behind a final customer's single connection point. Controllable units are required to be "switchable" between aggregators (through dedicated control units), restoring grid users' sovereignty over the hardware they have purchased and effectively separating hardware from aggregation markets. These rules represent a significant leap forward, posing substantial data management challenges for all stakeholders in the field. Relevant data exchange standards are currently discussed by ENTSO-E, the DSO Entity as well as industries to ensure the end-to-end interoperability of demand side flexibility data through harmonised ontologies, as defined in the **Common Information Model (CIM)**. Anyway, the markets they facilitate will not function without full digitalization and efficient data exchange environments, defined at European level to ensure level playing access to distributed controllable units (such as those associated with heat pumps and EVs).

## External references named in this chapter

| Reference | Form used in the source |
|---|---|
| Digitalising the energy system – EU action plan | `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52022DC0552` (footnote 5) |
| Energy Performance of Buildings (directive) | `https://energy.ec.europa.eu/topics/energy-efficiency/energy-efficient-buildings/energy-performance-buildings-directive_en` (footnote 6) |
| IDS-RAM 4 - Roles in the International data spaces | cited as "[3]" in §3.1.2 |
| network code on demand response | named, no legal citation given (§3.6) |
| new demand side flexibility code | named, no legal citation given (§3.3.1) |
| GDPR | named, no article citation given (§3.5.3) |
| Common Information Model (CIM) | named, no version or specification reference given (§3.6) |
| ENTSO-E · EU DSO Entity | named as drafting bodies (§3.6) |

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

Chapter 3 is largely descriptive prose. The **Force** column records the modality the source itself uses: `must` where the source writes *shall* / *must* / *required* / *need(s) to* / *prerequisite*; `should` where it writes *should*; `may` where it writes *may* / *might* / *can* / *permitted*; `informative` where the source states the item in plain declarative or future-descriptive terms with no modality. Rows marked `informative` are still concrete, checkable statements — they are not promoted to normative force here.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `CEEDS-BUC-01` | Every actor of the BUCs corresponds to a data space participant, with the role of data provider or data consumer. | informative | `Blueprint_CEEDS_v3.0.txt:455-459` |
| `CEEDS-BUC-02` | Data from diverse sources is integrated with standardized data models and ontologies, stated as "a crucial prerequisite for maximizing the advantages of the data spaces in the energy domain". | must | `Blueprint_CEEDS_v3.0.txt:427-429` |
| `CEEDS-BUC-03` | Size the technical components and conduct an economical evaluation for the deployment of energy communities, based on consumption and generation profiles as well as market data, weather data and the possibility of assets sharing business models. | informative | `Blueprint_CEEDS_v3.0.txt:565-567` |
| `CEEDS-BUC-04` | Provide the mechanisms for the collection and sharing of data, with appropriate granularity at the device level, of the energy consumption and generation, with the final goal of enabling flexibility and energy savings mechanisms. | informative | `Blueprint_CEEDS_v3.0.txt:568-570` |
| `CEEDS-BUC-05` | Extract approximated flexibility models for smart appliances (e.g., using non-intrusive load monitoring data), enabling an overall quantification of flexibility and estimation of energy savings from intelligent load control. | informative | `Blueprint_CEEDS_v3.0.txt:571-573` |
| `CEEDS-BUC-06` | The Service Provider offers, via its broker, the technical algorithms as services to which the Service Consumer has subscribed. | informative | `Blueprint_CEEDS_v3.0.txt:596-599` |
| `CEEDS-BUC-07` | Technical parameters (including the type of available devices, assets, and capacity constraints), pricing and financing specifications as well as consumption and generation data profiles are used as the inputs coming from the Data Provider. | informative | `Blueprint_CEEDS_v3.0.txt:603-605` |
| `CEEDS-BUC-08` | The consent for data sharing is obtained from the Data Owner. | informative | `Blueprint_CEEDS_v3.0.txt:605-606` |
| `CEEDS-BUC-09` | The data space Clearing House — a service for logging data exchange transactions relevant for clearing and billing as well as usage control — works as an intermediary to keep the log of the transactions. | informative | `Blueprint_CEEDS_v3.0.txt:606-608` |
| `CEEDS-BUC-10` | The output data are received by the Service Consumers and correspond to the optimal installed capacity, the estimated flexibility schedule and the pricing for internal and external transactions, differentiated according to the energy sharing mechanism. | informative | `Blueprint_CEEDS_v3.0.txt:608-610` |
| `CEEDS-BUC-11` | The provision of information regarding the required device maintenance is included as an additional service. | informative | `Blueprint_CEEDS_v3.0.txt:610-612` |
| `CEEDS-BUC-12` | The data exchange outputs allow improving the forecasts on available flexibility (i.e., aggregated demand side flexibility potential of the energy community). | informative | `Blueprint_CEEDS_v3.0.txt:612-613` |
| `CEEDS-BUC-13` | A data exchange environment built around data sovereignty guarantees is procured, allowing the translation from common legal contracts to smart contracts. | must | `Blueprint_CEEDS_v3.0.txt:617-619` |
| `CEEDS-BUC-14` | Smart contracts guide data exchange limits (i.e., usage policies). | informative | `Blueprint_CEEDS_v3.0.txt:618-619` |
| `CEEDS-BUC-15` | Smart contracts guide the long-term and post-exchange traceability of all data and associated data transactions. | informative | `Blueprint_CEEDS_v3.0.txt:619-620` |
| `CEEDS-BUC-16` | Pre and post data exchange guarantees are ensured with identity verification and validation of the involved organizations. | must | `Blueprint_CEEDS_v3.0.txt:620-623` |
| `CEEDS-BUC-17` | Traceability of data flows is ensured as part of a digital passport for data as an asset. | must | `Blueprint_CEEDS_v3.0.txt:623-624` |
| `CEEDS-BUC-18` | Real-time data exchange and streaming are required across the different federated actors of the electricity value chain. | must | `Blueprint_CEEDS_v3.0.txt:716-720` |
| `CEEDS-BUC-19` | A variety of domain-specific data exchange standards is taken advantage of through consistent data space dictionaries. | must | `Blueprint_CEEDS_v3.0.txt:718-720` |
| `CEEDS-BUC-20` | Reference DER data dictionaries are managed to enable plug-and-play registration of DER infrastructures in TSO-DSO flexibility markets. | informative | `Blueprint_CEEDS_v3.0.txt:756-757` |
| `CEEDS-BUC-21` | The associated data space should allow managing all types of DER integrating the latest power electronics, edge computing and data streaming technologies. | should | `Blueprint_CEEDS_v3.0.txt:760-762` |
| `CEEDS-BUC-22` | The associated data space should exchange relevant residential energy data obtained from the main smart meter as well as from any other accessible DER submeters/dedicated measurement devices. | should | `Blueprint_CEEDS_v3.0.txt:761-763` |
| `CEEDS-BUC-23` | The data space should be distributed through different federated cloud infrastructures. | should | `Blueprint_CEEDS_v3.0.txt:763-764` |
| `CEEDS-BUC-24` | The data space should enable consent based on data exchanges across actors. | should | `Blueprint_CEEDS_v3.0.txt:764` |
| `CEEDS-BUC-25` | Residential DER registration consists in messages to registers customers in the DSO flexibility register. | informative | `Blueprint_CEEDS_v3.0.txt:775-777` |
| `CEEDS-BUC-26` | Baseline data is provided, calculated by the service provider or the final customer, also based on weather/carbon/other data. | informative | `Blueprint_CEEDS_v3.0.txt:781-783` |
| `CEEDS-BUC-27` | Data exchange and communication requirements need to be tested for balancing services. | must | `Blueprint_CEEDS_v3.0.txt:787-790` |
| `CEEDS-BUC-28` | When flexibility is activated (either through a bare execution of a bid, or via set points), a controllable unit can receive these signals either via the Service Provider or directly from the System or Market Operator. | may | `Blueprint_CEEDS_v3.0.txt:791-800` |
| `CEEDS-BUC-29` | Service Providers may use the Kafka-based streaming infrastructure for communication with the market. | may | `Blueprint_CEEDS_v3.0.txt:800-803` |
| `CEEDS-BUC-30` | Service Providers may use the Kafka-based streaming infrastructure for communication with their units under control. | may | `Blueprint_CEEDS_v3.0.txt:800-803` |
| `CEEDS-BUC-31` | After the delivery phase, measurements at different points need to be transferred to the Flexibility Registry Operator. | must | `Blueprint_CEEDS_v3.0.txt:804-807` |
| `CEEDS-BUC-32` | Measurements are made available to the Settlement Responsible Party for service validation and perimeter correction. | must | `Blueprint_CEEDS_v3.0.txt:807-809` |
| `CEEDS-BUC-33` | Active network management regimes for network control need to be developed. | must | `Blueprint_CEEDS_v3.0.txt:835-836` |
| `CEEDS-BUC-34` | Advanced forecasting of loads and generation for resource scheduling and real-time control is required. | must | `Blueprint_CEEDS_v3.0.txt:836-837` |
| `CEEDS-BUC-35` | In their role as system operators, TSOs and DSOs are required to explore, evaluate, and deploy non-network alternatives that include the operation of market-based approaches such as frequency containment and reserves. | must | `Blueprint_CEEDS_v3.0.txt:839-841` |
| `CEEDS-BUC-36` | The development of new market-based approaches shall be non-discriminatory. | must | `Blueprint_CEEDS_v3.0.txt:843` |
| `CEEDS-BUC-37` | Services might be offered from all eligible participants (either aggregated or direct end-users) at different voltage levels. | may | `Blueprint_CEEDS_v3.0.txt:843-845` |
| `CEEDS-BUC-38` | The operation of the transmission and distribution networks shall be performed collaboratively between TSOs and DSOs. | must | `Blueprint_CEEDS_v3.0.txt:845-848` |
| `CEEDS-BUC-39` | TSOs and DSOs are involved in bilateral data-sharing agreements (facilitated by energy data spaces) towards exchanging flexibility requirements. | must | `Blueprint_CEEDS_v3.0.txt:848-852` |
| `CEEDS-BUC-40` | Optimal operation of power grids is pursued through federated flexibility registers, as defined through the new demand side flexibility code. | must | `Blueprint_CEEDS_v3.0.txt:852-856` |
| `CEEDS-BUC-41` | System operators engage in data sharing with FSP towards gaining increased visibility over available flexibility sources and proper clusters of them. | must | `Blueprint_CEEDS_v3.0.txt:856-858` |
| `CEEDS-BUC-42` | Novel (data-driven and intelligence-enabled) approaches are defined for the real-time or near-to-real-time aggregation of the available flexibility provided by distributed energy resources located in the distribution network. | must | `Blueprint_CEEDS_v3.0.txt:872-875` |
| `CEEDS-BUC-43` | Small-scale resources located in the distribution system are aggregated to be efficiently included in the operational planning of either DSO or TSO. | must | `Blueprint_CEEDS_v3.0.txt:875-877` |
| `CEEDS-BUC-44` | Tools enhancing the fast and efficient coordination between TSO and DSO should be developed, so that flexibility from the distribution system is transferred to the TSO. | should | `Blueprint_CEEDS_v3.0.txt:877-879` |
| `CEEDS-BUC-45` | Both System Operators obtain access to previously non-reachable data from DERs across their networks, including local demand data from flexible loads, RES generation data, flexibility-relevant data from storage assets/inverters and associated short- and mid-term forecasts. | must | `Blueprint_CEEDS_v3.0.txt:925-928` |
| `CEEDS-BUC-46` | Both System Operators fuse the acquired DER data with their own SCADA and metering data. | must | `Blueprint_CEEDS_v3.0.txt:928-929` |
| `CEEDS-BUC-47` | Use case #3 requires GIS data of MV/LV lines including information about electrical connection (cable or overhead line, length, type, routing). | must | `Blueprint_CEEDS_v3.0.txt:1004-1005` |
| `CEEDS-BUC-48` | Use case #3 requires transformer electrical data: Capacity (nominal apparent power), voltage primary & secondary, degree of load Velander's formula constants, etc. | must | `Blueprint_CEEDS_v3.0.txt:1006-1007` |
| `CEEDS-BUC-49` | Use case #3 requires SCADA Data: power grid measurements for voltage and current, power factor, tap changer positions at the 10 kV side of the 60/10 kV feeders, frequency measurements, active and reactive measurements for power generators on 10 kV feeders. | must | `Blueprint_CEEDS_v3.0.txt:1008-1010` |
| `CEEDS-BUC-50` | Use case #3 requires AMI Data - Consumers: smart metering data from MV & LV telemetered consumers (Active+, Reactive or Q1 or both). | must | `Blueprint_CEEDS_v3.0.txt:1011-1012` |
| `CEEDS-BUC-51` | Use case #3 requires AMI Data - Producers: smart metering data from MV & LV telemetered producers PV/ Wind (Active-, Active+, Reactive or Q1 or both). | must | `Blueprint_CEEDS_v3.0.txt:1013-1014` |
| `CEEDS-BUC-52` | Use case #3 requires metering data for non-telemetered: aggregated metering data for non-telemetered MV & LV consumers & producers. | must | `Blueprint_CEEDS_v3.0.txt:1015-1016` |
| `CEEDS-BUC-53` | Use case #3 requires grid-level flexibility forecasting on a 15-minute interval prior to real-time operation. | must | `Blueprint_CEEDS_v3.0.txt:1022-1023` |
| `CEEDS-BUC-54` | Use case #3 requires grid-level Demand and generation Forecasting on a 15-minute interval prior to real-time operation. | must | `Blueprint_CEEDS_v3.0.txt:1024-1025` |
| `CEEDS-BUC-55` | Use case #3 requires total generation: network peak and average total generation. | must | `Blueprint_CEEDS_v3.0.txt:1026` |
| `CEEDS-BUC-56` | Use case #3 requires total demand: network peak and average total demand. | must | `Blueprint_CEEDS_v3.0.txt:1027` |
| `CEEDS-BUC-57` | Use case #3 requires congestion problems: investigation and detection of network constraints violations. | must | `Blueprint_CEEDS_v3.0.txt:1028` |
| `CEEDS-BUC-58` | Use case #3 requires flexibility requirements based on the detected congestions. | must | `Blueprint_CEEDS_v3.0.txt:1029` |
| `CEEDS-BUC-59` | Use case #3 requires storage device operational data. | must | `Blueprint_CEEDS_v3.0.txt:1030` |
| `CEEDS-BUC-60` | Use case #3 requires flexibility offers: offers of the available flexibility at each time instant/period from the FSPs. | must | `Blueprint_CEEDS_v3.0.txt:1031` |
| `CEEDS-BUC-61` | Offer a standardized roaming booking service for electric vehicle users and Charing Point Operators (CPOs) across Europe. | informative | `Blueprint_CEEDS_v3.0.txt:1058-1059` |
| `CEEDS-BUC-62` | Provide DSOs/TSOs with charging consumptions schedule based on CPOs' charging schedules and reserved powers, to enhance the accuracy of system operators' forecasts and planned operations. | informative | `Blueprint_CEEDS_v3.0.txt:1060-1062` |
| `CEEDS-BUC-63` | Provide flexibility services to the DSOs/TSOs to optimise smart grids management. | informative | `Blueprint_CEEDS_v3.0.txt:1068` |
| `CEEDS-BUC-64` | An EVU who wants to book a charging service must connect to an eMSP, as an application or platform. | must | `Blueprint_CEEDS_v3.0.txt:1073-1074` |
| `CEEDS-BUC-65` | All eMSP services require a subscription to the eMSP from the EV user. | must | `Blueprint_CEEDS_v3.0.txt:1044-1046` |
| `CEEDS-BUC-66` | Users can search for available charging points according to their criteria of location, time and technical specifications for charging. | may | `Blueprint_CEEDS_v3.0.txt:1077-1078` |
| `CEEDS-BUC-67` | The user can compare the different rates applied according to operator and charging criteria. | may | `Blueprint_CEEDS_v3.0.txt:1078-1079` |
| `CEEDS-BUC-68` | The user can reserve a charging slot by specifying the information required for accessing the charging pool, charging his car, and paying for the session (physical characteristics, means of authentication at the charging point, etc.). | may | `Blueprint_CEEDS_v3.0.txt:1081-1083` |
| `CEEDS-BUC-69` | The user can access an estimate of the final charge price, calculated on the selected criteria and provided details. | may | `Blueprint_CEEDS_v3.0.txt:1083-1084` |
| `CEEDS-BUC-70` | Once the charge has been completed, the user is able to access his detailed invoice from the eMSP application and is charged the final amount due. | informative | `Blueprint_CEEDS_v3.0.txt:1084-1086` |
| `CEEDS-BUC-71` | The data on the energy consumption, associated with the scheduled and performed charging session, is exchanged between the EMSP and the DSO/TSO to improve the load forecasting and electrical grid operations. | informative | `Blueprint_CEEDS_v3.0.txt:1090-1092` |
| `CEEDS-BUC-72` | The DSP/TSOs can send flexibility orders to EMSP to modify the charging schedule. | may | `Blueprint_CEEDS_v3.0.txt:1092-1093` |
| `CEEDS-BUC-73` | The EMSP, the CPO and the EMRSP are registered on the marketplace of a European data space. | must | `Blueprint_CEEDS_v3.0.txt:1096-1099` |
| `CEEDS-BUC-74` | The EMRSP has subscribed to the CPO's service and the CPO has accepted it. | must | `Blueprint_CEEDS_v3.0.txt:1099-1100` |
| `CEEDS-BUC-75` | The EMSP has subscribed to the EMRSP's service and the EMRSP has accepted it. | must | `Blueprint_CEEDS_v3.0.txt:1100-1101` |
| `CEEDS-BUC-76` | The EMRSP exchanges its tariffs with CPO and EMSP. | must | `Blueprint_CEEDS_v3.0.txt:1101` |
| `CEEDS-BUC-77` | Develop more robust algorithms for optimizing the O&M of renewable energy assets by leveraging data from multiple renewable energy plant owners. | informative | `Blueprint_CEEDS_v3.0.txt:1155-1158` |
| `CEEDS-BUC-78` | Develop data analytics to enable efficient integration of distributed energy sources into the smart grid by monitoring data from different actors such as consumers and producers and data from the grid itself, anticipating potential issues like congestion or voltage volatility. | informative | `Blueprint_CEEDS_v3.0.txt:1159-1163` |
| `CEEDS-BUC-79` | Data exchange amongst different actors of the energy system is fostered while ensuring data security, privacy and sovereignty. | must | `Blueprint_CEEDS_v3.0.txt:1187-1188` |
| `CEEDS-BUC-80` | Data is exchanged through the Common European Energy Data Space through the so-called connectors ensuring data privacy, security and sovereignty. | informative | `Blueprint_CEEDS_v3.0.txt:1215-1216` |
| `CEEDS-BUC-81` | Datasets such as prosumer data that may include personal information need to comply with GDPR. | must | `Blueprint_CEEDS_v3.0.txt:1203-1205` |
| `CEEDS-BUC-82` | Use case #5 exchanges SCADA data for RES operation. | informative | `Blueprint_CEEDS_v3.0.txt:1197-1198` |
| `CEEDS-BUC-83` | Use case #5 exchanges meteorological data. | informative | `Blueprint_CEEDS_v3.0.txt:1197-1198` |
| `CEEDS-BUC-84` | Use case #5 exchanges smart grid data. | informative | `Blueprint_CEEDS_v3.0.txt:1197-1198` |
| `CEEDS-BUC-85` | Use case #5 exchanges prosumer energy consumption (smart meter) data. | informative | `Blueprint_CEEDS_v3.0.txt:1197-1198` |
| `CEEDS-BUC-86` | For O&M optimization purposes, the scope of data exchange is global, aiming to gather real operational data from similar assets in diverse operating conditions worldwide. | informative | `Blueprint_CEEDS_v3.0.txt:1200-1202` |
| `CEEDS-BUC-87` | For smart grid integration, the scope of data exchange is more localized or regional. | informative | `Blueprint_CEEDS_v3.0.txt:1202-1203` |
| `CEEDS-BUC-88` | A "Technical resource" is an individual power generation, energy storage, or demand module. | informative | `Blueprint_CEEDS_v3.0.txt:1288` |
| `CEEDS-BUC-89` | A "Controllable unit" is a single technical resource or a group of technical resources behind the same connection point, provided that these technical resources can be collectively controlled. | informative | `Blueprint_CEEDS_v3.0.txt:1289-1291` |
| `CEEDS-BUC-90` | The controllable unit remains under the full sovereignty of the final customer, who has the authority to decide which aggregator or service provider will market the flexibility of the asset. | must | `Blueprint_CEEDS_v3.0.txt:1291-1293` |
| `CEEDS-BUC-91` | A "Service providing unit" (SPU) is a single controllable unit or a group of controllable units, a "service providing group" (SPG), connected to the same connection point. | informative | `Blueprint_CEEDS_v3.0.txt:1294-1296` |
| `CEEDS-BUC-92` | SPUs and SPGs are defined by the service provider to deliver local or balancing services. | must | `Blueprint_CEEDS_v3.0.txt:1295-1296` |
| `CEEDS-BUC-93` | A "Service provider" or "aggregator" is a market participant with a legal or contractual obligation to supply local or balancing services from at least one SPU or SPG. | informative | `Blueprint_CEEDS_v3.0.txt:1297-1298` |
| `CEEDS-BUC-94` | High-level real-time monitoring requirements will need to be managed by service providers. | must | `Blueprint_CEEDS_v3.0.txt:1304-1306` |
| `CEEDS-BUC-95` | The provision of local services must be coordinated and potentially constrained by system operators to avoid violating grid limitations, through local congestion-based markets and, potentially, flexible connection agreements. | must | `Blueprint_CEEDS_v3.0.txt:1306-1308` |
| `CEEDS-BUC-96` | Submetering, together with embedded measurement devices in control unit equipment, will be integrated into the European regulatory framework. | informative | `Blueprint_CEEDS_v3.0.txt:1308-1310` |
| `CEEDS-BUC-97` | Multiple FSP, as well as multiple suppliers, will be permitted to operate behind a final customer's single connection point. | may | `Blueprint_CEEDS_v3.0.txt:1310-1311` |
| `CEEDS-BUC-98` | Controllable units are required to be "switchable" between aggregators (through dedicated control units). | must | `Blueprint_CEEDS_v3.0.txt:1311-1313` |
| `CEEDS-BUC-99` | Relevant data exchange standards are currently discussed by ENTSO-E, the DSO Entity as well as industries to ensure the end-to-end interoperability of demand side flexibility data through harmonised ontologies, as defined in the Common Information Model (CIM). | informative | `Blueprint_CEEDS_v3.0.txt:1315-1317` |
| `CEEDS-BUC-100` | The markets facilitated by these rules will not function without full digitalization and efficient data exchange environments, defined at European level to ensure level playing access to distributed controllable units. | must | `Blueprint_CEEDS_v3.0.txt:1317-1320` |

## Open questions

Ambiguities, inconsistencies and gaps found in chapter 3. These are reported, not resolved.

**Scenario counts and totals**

1. §3.3 does not state how many scenarios use case #3 has. Table 6 contains **six** rows; Figure 6 contains **four** fragments, and the two sets do not correspond one-to-one (Table 6's "Performant data search across federated data spaces" and "Sharing, trading and bartering of raw and derivative data assets" both appear to map onto the single Figure 6 fragment "Searching, Sharing, and Trading Data"; Table 6's "AI-enabled Grid-level flexibility profiling and forecasting" has no dedicated fragment).
2. §3.5.3 is titled "Scenarios" but contains no scenario descriptions in prose — it discusses datasets, data ownership and willingness to share. The scenarios exist only in Table 8 (four rows) and Figure 9 (four fragments).
3. §3.2.3 consists solely of Table 5 and Figure 5; there is no prose introducing or bounding the nine scenarios.

**Scenario naming inconsistencies within a single use case**

4. Use case #1 scenario 3 is named "Computation of Internal Transaction Price based on REC/CEC Operation" in the §3.1.3 prose but "Computation of energy price within the REC / CEC" in both Table 4 and Figure 4.
5. Use case #1 scenario 2 is "Estimation of Flexibility Potential and Energy Cost Savings from Thermal Domestic Loads" in prose, "Estimation of flexibility potential and energy savings from thermal domestic loads" in Table 4 (the word "cost" is absent), and "Estimation of flexibility potential and energy cost savings from thermal domestic loads" in Figure 4.
6. Use case #5 fragment names in Figure 9 differ in capitalisation and completeness from the Table 8 scenario names ("RES Smart Grid Integration" vs "RES smart grid integration"; "Optimal RES Sizing" vs "Optimal RES sizing (prosumer/community)"; "DSO Resources Optimal Location" vs "DSO resources optimal location").

**Actor naming — the largest source of ambiguity in this chapter**

7. **Use case #1**: the actors in Table 4 (Consumer, Energy service company, Energy trader, Market information aggregator, Resource aggregator, FSP, Sub-meter data hub operator) and the lifelines in Figure 4 (Service Consumer, REC Service Provider, Data Cooperative Service Provider, Regulator Service Provider, PV Public Data) are **disjoint sets**. No mapping is given. §3.1.2 introduces a third set (Service Provider, Service Consumer, Data Provider, Data Owner, broker, Clearing House) attributed to reference [3] (IDS-RAM 4).
8. **Use case #2**: the actors in Table 5 (Prosumer, Resource aggregator, Consent administrator, Flexibility register, Flexible product qualifier, DER, Local energy management, Weather forecast provider, FSP, Balancing responsible party, Data provider, Resource provider, Balancing service provider, Market operator, TSO, DSO, Flexibility buyer, Flexibility settlement party, Metered data responsible, Metered data collector) do not match the four Figure 5 lifelines (System Operators, Flexibility Service Provider, Technical Aggregator, Prosumer/DER Owner). "Technical Aggregator" appears **only** in Figure 5 and is not defined anywhere in chapter 3.
9. **Use case #4**: the chapter uses `eMSP` (§3.4.1 definition, Table 7 first row) and `EMSP` (§3.4.2, Table 7 second row) interchangeably; `TSO/DSO`, `DSO/TSO` and `DSP/TSOs` all appear (the last presumably a typo). §3.4.1 defines "Electro Mobility Roaming Service Provider (EMRSP)" while Figure 7 labels the same lifeline "e-Mobility Roaming Service Provider".
10. **Use case #4**: "AI Service Provider" is defined as one of the five interfaced actors in §3.4.1 but appears in neither row of Table 7; it appears only as a lifeline in Figure 8.
11. **Use case #5**: Table 8 lists "DSO, Consumer/ Produces, Data analytics service providers" — "Produces" appears to be a typo for "Producers". Figure 9 introduces the lifeline "Prosumer/DER Owner", which is not among the Table 8 actors (which use "prosumers" and "Consumer/Producer").
12. Chapter 3 never states which role model its actor names come from. Names such as "Balancing responsible party", "Metered data responsible", "Metered data collector", "Flexibility settlement party", "Flexibility Registry Operator" and "Settlement Responsible Party" are used without definition in this chapter. (The blueprint names the Harmonised Electricity Market Role Model (HEMRM) at `Blueprint_CEEDS_v3.0.txt:314` and IDS-RAM 4 roles as reference [3], but §3 maps its actors onto neither.)
13. Table 6's Actors column mixes actor and role ("Data asset consumers (role obtained by TSOs, DSOs and FSPs)"). The chapter does not define the actor/role distinction it is applying.
14. "Flexibility register" (Table 5, an actor), "Flexibility Registry Operator" (Table 5, additional information) and "federated flexibility registers" (§3.3.1) are used without stating whether they denote the same thing.
15. Table 2's "Key Actors" for BUC #1 (Energy service companies, Energy traders, Market information aggregators, Resource aggregators) omits Consumer, FSP and Sub-meter data hub operator, which Table 4 lists for every scenario of that BUC. Similar partial coverage applies to the other BUCs.

**Legal and standards references**

16. §3.6 refers to "the network code on demand response", §3.3.1 to "the new demand side flexibility code" and §3.3.2 to "the recent flexibility code deployment". The chapter does not state whether these denote the same instrument, and gives **no legal citation** (no instrument number, no article) for any of them — unlike the EU action plan and the Energy Performance of Buildings directive, which carry URLs.
17. §3.6 is titled "Network codes requirements" (plural) in both the body and the table of contents, but discusses a single network code; the chapter introduction (`:548-549`) calls the same material "new EU grid codes regulation".
18. The Common Information Model (CIM) is named as the source of "harmonised ontologies" without a specification, series or version reference (§3.6).
19. GDPR is invoked without an article reference (§3.5.3).

**Structural and editorial**

20. Section-heading style is inconsistent: §§3.1.1, 3.2.1, 3.4.1 and 3.5.1 are "Scopes" (plural) while §3.3.1 is "Scope"; §3.4 is titled "Use-case #4" while §§3.1, 3.2, 3.3 and 3.5 use "Use case #N"; §§3.1, 3.3 and 3.4 use a hyphen between the number and the title while §§3.2 and 3.5 use an en dash.
21. The BUC #2 title differs between the chapter's list (`:437-438`, "Residential home energy management integrating Distributed Energy Resources (DER) flexibility aggregation") and the §3.2 section heading ("… integrating DER flexibility aggregation").
22. Table 3's cells are sentence fragments describing themes, not statements; they are not usable as requirements and are reproduced here only as the source's taxonomy.
23. Table 5 is the only scenario table in the chapter without *Triggering events*, *Pre-condition* and *Post-condition* columns, so the nine BUC #2 scenarios cannot be benchmarked on the same basis as the scenarios of the other four BUCs.
24. Spellings preserved verbatim from the source that appear to be errors: "request tarif data" / "transfer tarif data" (Figure 4); "Charging Point Location Retrival" (Figure 7); "Dend Storage Data" (Figure 9); "Charing Point Operators (CPOs)" (§3.4.1); "Registration consists in messages to registers customers" (Table 5); "Consumer/ Produces" (Table 8); "the DSP/TSOs can send flexibility orders" (§3.4.2). §3.3.2 contains a stray sentence break: "the data sharing functions enabled through them. for network operators, lies on the fact that…".
25. §3.1.3's prose description of scenario 1 contains an unclosed parenthesis: "request data (e.g., real consumption profiles (historical data), and solve optimization problems".
26. Figures 4–9 carry no legend distinguishing synchronous from asynchronous messages, and none of the messages carries a payload schema, protocol or standard reference. The data flows are therefore named but not typed.
