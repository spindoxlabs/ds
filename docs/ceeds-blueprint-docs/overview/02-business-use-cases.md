# 02 — Business Use Cases for Energy

## Overview

Five reference Business Use Cases (BUCs) form the backbone of CEEDS. They are derived from the EU action plan "Digitalising the energy system" and the EDSCP cluster projects. Every actor in these BUCs corresponds to a data space participant with the role of data provider or data consumer.

## BUC Summary

| # | Title | Scope | Key Actors | Data Exchange Focus |
|---|---|---|---|---|
| 1 | Collective self-consumption and optimised sharing for energy communities | REC/CEC energy sharing optimisation | Energy service companies, traders, market info aggregators, resource aggregators | Data collection/sharing for flexibility and energy savings; non-intrusive load monitoring |
| 2 | Residential home energy management integrating DER flexibility aggregation | DER optimisation to reduce grid congestions and critical peak prices | Prosumers, DER operators, FSP, local energy management providers | Real-time data exchange and streaming; IoT, edge computing, V2X |
| 3 | TSO-DSO coordination for flexibility | Enhancing resilience and RES integration; non-cable solutions for congestion/voltage | TSOs, DSOs, DER operators, FSP | Forecasting loads/generation for resource scheduling; real-time control |
| 4 | Electromobility: services roaming, load forecasting and schedule planning | EV charging infrastructure optimisation; predictive charging for grid management | CPO, eMSP, EMRSP, EV users | Booking/scheduling of EV charging; predictive analytics for demand |
| 5 | Renewables O&M optimisation and grid integration | O&M cost reduction via cross-portfolio AI; efficient DER grid integration | RES plant owners/operators, DSOs, OEMs, component manufacturers, analytics providers | Fault detection, automated diagnosis, maintenance prescription; smart grid analytics |

## BUC #1 — Energy Communities

**Objective**: Instantiation and operation of Jointly Acting Self-Consumers (JASC), Residential Energy Communities (RECs) and Commercial Energy Communities (CECs).

**Sub-use cases**:
1. DER sizing and economic evaluation of REC/CEC business model
2. Estimation of flexibility potential and energy cost savings from thermal domestic loads
3. Computation of internal transaction price based on REC/CEC operation

**Data space value**: Multiple stakeholders and service providers require data sovereignty guarantees, translation from legal contracts to smart contracts, usage policies governing data exchange limits, and post-exchange traceability.

## BUC #2 — Residential DER Flexibility

**Objective**: Prosumers contribute to flexibility markets via home-level DER (heat pumps, EV chargers, batteries, smart heating).

**Scenarios**: Energy/carbon monitoring, DER registration, home energy optimisation, baseline calculation, flexibility intraday calculation, flexibility bidding, activation, observability, transaction management.

**Key technical aspects**: Kafka-based streaming infrastructure, real-time data exchange, edge computing, V2X interactions, federated cloud architectures.

## BUC #3 — TSO-DSO Coordination

**Objective**: Enhanced coordination between TSOs and DSOs for flexibility procurement, critical event prioritisation, and collaborative scheduling.

**Data needs**: GIS data (MV/LV lines), transformer data, SCADA data, AMI data (consumers/producers), grid-level flexibility/demand/generation forecasting (15-min intervals), storage device data, flexibility offers.

**Key technical aspects**: Federated flexibility registers, demand side flexibility code, AI-enabled forecasting, real-time DER data streaming.

## BUC #4 — Electromobility

**Objective**: Standardised pan-European EV booking/roaming service; charging consumption data exchange with TSOs/DSOs for grid management; flexibility services from EVs.

**Scenarios**: EV Booking Roaming Service, EV Flexibility Service.

**Key actors**: CPO (charging infrastructure), eMSP (user-facing services), EMRSP (roaming intermediary), EVU (vehicle user), AI Service Provider.

## BUC #5 — Renewables O&M

**Objective**: Cross-portfolio AI for optimised O&M; efficient grid integration of distributed renewables.

**Scenarios**: RES O&M optimisation, RES smart grid integration, optimal RES sizing, DSO resources optimal location.

**Key insight**: Data willingness varies by technology — PV owners are open to sharing; wind OEMs are less inclined (data is competitive advantage for O&M services business model shift).

## Grid Codes Requirements

The CEEDS integrates with upcoming EU network codes on demand response (relevant to BUC #1 and #2):

- **Technical resource**: Individual power generation, energy storage, or demand module
- **Controllable unit**: Single or grouped technical resources behind same connection point, under customer sovereignty
- **Service providing unit (SPU)**: Single controllable unit or group delivering local/balancing services
- **Service provider / Aggregator**: Market participant supplying services from SPUs/SPGs

Key regulatory implications:
- Submetering integrated into EU regulatory framework
- Multiple FSPs and suppliers permitted behind single connection point
- Controllable units must be "switchable" between aggregators
- Hardware separated from aggregation markets
